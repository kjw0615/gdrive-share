"""Server-only PostgreSQL configuration; no credentials are returned to the browser."""
import os
from pathlib import Path
from urllib.parse import urlparse, unquote
import psycopg
from psycopg.rows import dict_row

DB_KEYS = {'DATABASE_URL', 'POSTGRES_URL', 'POSTGRES_URL_NON_POOLING', 'POSTGRES_HOST', 'POSTGRES_PORT', 'POSTGRES_USER', 'POSTGRES_PASSWORD', 'POSTGRES_DATABASE', 'POSTGRES_DB'}


def load_db_config():
    if os.getenv('VERCEL'):
        return
    path = Path(__file__).with_name('.env')
    if path.exists():
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            key, value = key.strip(), value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                value = value[1:-1]
            if key in DB_KEYS:
                os.environ.setdefault(key, value)


def connect():
    load_db_config()
    url = os.getenv('DATABASE_URL') or os.getenv('POSTGRES_URL') or os.getenv('POSTGRES_URL_NON_POOLING')
    if url:
        parsed = urlparse(url)
        if parsed.scheme not in ('postgres', 'postgresql') or not parsed.hostname:
            raise RuntimeError('Invalid database URL')
        settings = dict(host=parsed.hostname, port=parsed.port or 5432, user=unquote(parsed.username or ''), password=unquote(parsed.password or ''), dbname=unquote(parsed.path.lstrip('/') or 'postgres'))
    else:
        settings = dict(host=os.getenv('POSTGRES_HOST'), port=int(os.getenv('POSTGRES_PORT', '5432')), user=os.getenv('POSTGRES_USER'), password=os.getenv('POSTGRES_PASSWORD'), dbname=os.getenv('POSTGRES_DATABASE') or os.getenv('POSTGRES_DB') or 'postgres')
        if not all(settings.get(k) for k in ('host', 'user', 'password')):
            raise RuntimeError('Database configuration is missing')
    return psycopg.connect(**settings, sslmode='require', connect_timeout=10, prepare_threshold=None, row_factory=dict_row, options='-c statement_timeout=8000')
