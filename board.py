"""Password-protected guest board. All SQL values use bound parameters."""
import uuid
from pathlib import Path
from urllib.parse import urlparse
import psycopg
from flask import Blueprint, Response, jsonify, request, abort
from werkzeug.security import generate_password_hash, check_password_hash
from db import connect
from admin import current_admin, require_csrf

board = Blueprint('board', __name__)
PUBLIC_FIELDS = 'id, title, author, content, version, created_at, updated_at'


def serialize(row):
    return {key: (value.isoformat() if hasattr(value, 'isoformat') else str(value) if isinstance(value, uuid.UUID) else value) for key, value in row.items() if key != 'password_hash'}


def input_data():
    if not request.is_json:
        abort(415, description='JSON 형식으로 요청하세요.')
    origin = request.headers.get('Origin')
    if origin and urlparse(origin).netloc != request.host:
        abort(403, description='다른 사이트의 요청은 허용하지 않습니다.')
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(400, description='입력 형식을 확인하세요.')
    return data


def text(data, key, minimum, maximum, label):
    value = data.get(key)
    if not isinstance(value, str):
        abort(400, description=label + '을 확인하세요.')
    value = value.strip() if key != 'password' else value
    if not minimum <= len(value) <= maximum:
        abort(400, description=f'{label}: {minimum}~{maximum}자로 입력하세요.')
    return value


def fields(data):
    return (text(data, 'title', 1, 200, '제목'), text(data, 'author', 1, 60, '작성자'), text(data, 'content', 1, 50000, '내용'))


@board.get('/board')
def page():
    return Response(Path(__file__).with_name('board.html').read_bytes(), mimetype='text/html')


@board.get('/api/board/posts')
def listing():
    try:
        page = max(1, min(10000, int(request.args.get('page', '1'))))
    except ValueError:
        abort(400, description='페이지 번호를 확인하세요.')
    query = request.args.get('q', '').strip()[:200]
    pattern = '%' + query.replace('!', '!!').replace('%', '!%').replace('_', '!_') + '%'
    where = "deleted_at IS NULL AND (title ILIKE %s ESCAPE '!' OR content ILIKE %s ESCAPE '!' OR author ILIKE %s ESCAPE '!')"
    with connect() as connection:
        total = connection.execute('SELECT count(*) AS total FROM public.jw_board_posts WHERE ' + where, (pattern, pattern, pattern)).fetchone()['total']
        rows = connection.execute('SELECT id,title,author,version,created_at,updated_at FROM public.jw_board_posts WHERE ' + where + ' ORDER BY created_at DESC,id LIMIT 15 OFFSET %s', (pattern, pattern, pattern, (page-1)*15)).fetchall()
    return jsonify(posts=[serialize(row) for row in rows], total=total, page=page, page_size=15)


@board.post('/api/board/posts')
def create():
    data = input_data()
    title, author, content = fields(data)
    password = text(data, 'password', 8, 128, '글 비밀번호')
    password_hash = generate_password_hash(password, method='pbkdf2:sha256:600000')
    with connect() as connection:
        row = connection.execute('INSERT INTO public.jw_board_posts (id,title,author,content,password_hash) VALUES (%s,%s,%s,%s,%s) RETURNING ' + PUBLIC_FIELDS, (uuid.uuid4(), title, author, content, password_hash)).fetchone()
    return jsonify(post=serialize(row)), 201


@board.get('/api/board/posts/<uuid:post_id>')
def detail(post_id):
    with connect() as connection:
        row = connection.execute('SELECT ' + PUBLIC_FIELDS + ' FROM public.jw_board_posts WHERE id=%s AND deleted_at IS NULL', (post_id,)).fetchone()
    if not row:
        abort(404, description='글을 찾을 수 없습니다.')
    return jsonify(post=serialize(row))


@board.route('/api/board/posts/<uuid:post_id>', methods=['PATCH', 'DELETE'])
def change(post_id):
    data = input_data()
    session = current_admin()
    if session and request.method == 'PATCH':
        abort(403, description='관리자는 글을 수정할 수 없습니다.')
    if session:
        require_csrf(session)
    password = None if session else text(data, 'password', 8, 128, '글 비밀번호')
    values = fields(data) if request.method == 'PATCH' else None
    if request.method == 'PATCH' and (type(data.get('version')) is not int or data['version'] < 1):
        abort(400, description='글 버전이 올바르지 않습니다.')
    with connect() as connection:
        row = connection.execute('SELECT password_hash,version FROM public.jw_board_posts WHERE id=%s AND deleted_at IS NULL FOR UPDATE', (post_id,)).fetchone()
        if not row:
            abort(404, description='글을 찾을 수 없습니다.')
        if not session and not check_password_hash(row['password_hash'], password):
            abort(403, description='글 비밀번호가 일치하지 않습니다.')
        if request.method == 'DELETE':
            connection.execute('UPDATE public.jw_board_posts SET deleted_at=now(),updated_at=now(),version=version+1 WHERE id=%s', (post_id,))
            return jsonify(deleted=True)
        if data['version'] != row['version']:
            abort(409, description='글이 변경되었습니다. 다시 열어 확인하세요.')
        updated = connection.execute('UPDATE public.jw_board_posts SET title=%s,author=%s,content=%s,updated_at=now(),version=version+1 WHERE id=%s RETURNING ' + PUBLIC_FIELDS, (*values, post_id)).fetchone()
    return jsonify(post=serialize(updated))


@board.errorhandler(psycopg.Error)
@board.errorhandler(RuntimeError)
def database_error(error):
    return jsonify(error='게시판 DB 연결 또는 테이블 설정을 확인하세요.'), 503


@board.errorhandler(400)
@board.errorhandler(403)
@board.errorhandler(404)
@board.errorhandler(409)
@board.errorhandler(415)
def board_error(error):
    return jsonify(error=error.description), error.code
