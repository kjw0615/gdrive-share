"""DB-backed administrator authentication and revocable, expiring sessions."""
import hashlib
import hmac
import os
import secrets
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlparse
import psycopg
from flask import Blueprint, abort, g, jsonify, request
from werkzeug.security import generate_password_hash, check_password_hash
from db import connect

admin = Blueprint('admin', __name__)
COOKIE = 'jw_admin_session'
SESSION_SECONDS = 60 * 60

# Required runtime bootstrap; kept in code so deployment needs no SQL files.
ADMIN_SCHEMA_SQL = '''
CREATE TABLE IF NOT EXISTS public.jw_admin_credentials (
    id smallint PRIMARY KEY CHECK (id = 1),
    password_hash text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS public.jw_admin_sessions (
    token_hash char(64) PRIMARY KEY,
    csrf_token text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL
);
CREATE INDEX IF NOT EXISTS jw_admin_sessions_expiry_idx ON public.jw_admin_sessions (expires_at);
CREATE TABLE IF NOT EXISTS public.jw_admin_login_limits (
    client_hash char(64) PRIMARY KEY,
    failures integer NOT NULL DEFAULT 0,
    locked_until timestamptz,
    updated_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE public.jw_admin_credentials ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.jw_admin_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.jw_admin_login_limits ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.jw_admin_credentials, public.jw_admin_sessions, public.jw_admin_login_limits FROM PUBLIC, anon, authenticated;
'''



def seed_password():
    value = os.getenv('SUPER_PASSWORD', '')
    if value or os.getenv('VERCEL'):
        return value
    path = Path(__file__).with_name('.env')
    if path.exists():
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            if '=' not in line or line.lstrip().startswith('#'):
                continue
            key, value = line.split('=', 1)
            if key.strip() == 'SUPER_PASSWORD':
                value = value.strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                    value = value[1:-1]
                return value
    return ''


def initialize_admin():
    with connect() as connection:
        connection.execute('SELECT pg_advisory_xact_lock(79120413)')
        tables = connection.execute("SELECT to_regclass('public.jw_admin_credentials') IS NOT NULL AND to_regclass('public.jw_admin_sessions') IS NOT NULL AND to_regclass('public.jw_admin_login_limits') IS NOT NULL AS ready").fetchone()
        if not tables['ready']:
            connection.execute(ADMIN_SCHEMA_SQL, prepare=False)
        existing = connection.execute('SELECT id FROM public.jw_admin_credentials WHERE id=1').fetchone()
        if existing:
            return False
        password = seed_password()
        if not password:
            raise RuntimeError('SUPER_PASSWORD is required for first initialization')
        connection.execute('INSERT INTO public.jw_admin_credentials (id,password_hash) VALUES (1,%s)', (generate_password_hash(password, method='pbkdf2:sha256:600000'),))
        return True


def current_admin():
    if hasattr(g, 'admin_session'):
        return g.admin_session
    token = request.cookies.get(COOKIE, '')
    if not token or len(token) > 128:
        g.admin_session = None
        return None
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    with connect() as connection:
        row = connection.execute('SELECT token_hash,csrf_token,expires_at FROM public.jw_admin_sessions WHERE token_hash=%s AND expires_at>now()', (token_hash,)).fetchone()
    g.admin_session = row
    return row


def require_csrf(session):
    supplied = request.headers.get('X-Admin-CSRF', '')
    if not session or not hmac.compare_digest(supplied, session['csrf_token']):
        abort(403, description='관리자 인증 정보가 올바르지 않습니다. 다시 로그인하세요.')


def input_data():
    if not request.is_json:
        abort(415, description='JSON 요청이 필요합니다.')
    origin = request.headers.get('Origin')
    if origin and urlparse(origin).netloc != request.host:
        abort(403, description='다른 사이트의 요청은 허용하지 않습니다.')
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(400, description='요청을 확인하세요.')
    return data


@admin.get('/api/admin/status')
def status():
    session = current_admin()
    if not session:
        return jsonify(authenticated=False)
    return jsonify(authenticated=True, csrf=session['csrf_token'], expires_at=session['expires_at'].isoformat())


@admin.post('/api/admin/login')
def login():
    data = input_data()
    password = data.get('password')
    if not isinstance(password, str) or not 1 <= len(password) <= 1024:
        abort(400, description='관리자 비밀번호를 입력하세요.')
    client_hash = hashlib.sha256((request.remote_addr or 'unknown').encode()).hexdigest()
    failed = False
    with connect() as connection:
        credential = connection.execute('SELECT password_hash FROM public.jw_admin_credentials WHERE id=1').fetchone()
        if not credential:
            return jsonify(error='관리자 초기 설정을 확인하세요.'), 503
        connection.execute('INSERT INTO public.jw_admin_login_limits (client_hash) VALUES (%s) ON CONFLICT DO NOTHING', (client_hash,))
        limits = connection.execute('SELECT failures,locked_until FROM public.jw_admin_login_limits WHERE client_hash=%s FOR UPDATE', (client_hash,)).fetchone()
        now = datetime.now(timezone.utc)
        if limits['locked_until'] and limits['locked_until'] > now:
            return jsonify(error='로그인 시도가 많습니다. 15분 후 다시 시도하세요.'), 429
        if not check_password_hash(credential['password_hash'], password):
            failures = 1 if limits['locked_until'] else limits['failures'] + 1
            connection.execute('UPDATE public.jw_admin_login_limits SET failures=%s,locked_until=%s,updated_at=now() WHERE client_hash=%s', (failures, now+timedelta(minutes=15) if failures>=5 else None, client_hash))
            failed = True
        else:
            connection.execute('UPDATE public.jw_admin_login_limits SET failures=0,locked_until=NULL,updated_at=now() WHERE client_hash=%s', (client_hash,))
            old_token = request.cookies.get(COOKIE)
            if old_token:
                connection.execute('DELETE FROM public.jw_admin_sessions WHERE token_hash=%s', (hashlib.sha256(old_token.encode()).hexdigest(),))
            connection.execute('DELETE FROM public.jw_admin_sessions WHERE expires_at<=now()')
            token = secrets.token_urlsafe(48)
            csrf = secrets.token_urlsafe(32)
            expiry = now + timedelta(seconds=SESSION_SECONDS)
            connection.execute('INSERT INTO public.jw_admin_sessions (token_hash,csrf_token,expires_at) VALUES (%s,%s,%s)', (hashlib.sha256(token.encode()).hexdigest(), csrf, expiry))
    if failed:
        abort(403, description='관리자 비밀번호가 일치하지 않습니다.')
    response = jsonify(authenticated=True, csrf=csrf, expires_at=expiry.isoformat())
    response.set_cookie(COOKIE, token, max_age=SESSION_SECONDS, httponly=True, secure=bool(os.getenv('VERCEL')) or request.is_secure, samesite='Strict', path='/')
    return response


@admin.post('/api/admin/logout')
def logout():
    input_data()
    session = current_admin()
    if session:
        require_csrf(session)
        with connect() as connection:
            connection.execute('DELETE FROM public.jw_admin_sessions WHERE token_hash=%s', (session['token_hash'],))
    response = jsonify(authenticated=False)
    response.delete_cookie(COOKIE, path='/', httponly=True, secure=bool(os.getenv('VERCEL')) or request.is_secure, samesite='Strict')
    return response


@admin.errorhandler(psycopg.Error)
@admin.errorhandler(RuntimeError)
def database_error(error):
    return jsonify(error='관리자 인증 DB 설정을 확인하세요.'), 503


@admin.errorhandler(400)
@admin.errorhandler(403)
@admin.errorhandler(415)
def request_error(error):
    return jsonify(error=error.description), error.code
