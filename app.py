"""Google Drive board: Flask WSGI application for Vercel and local development."""
import json
import os
import re
from flask import Flask, Response, jsonify, redirect, request
from urllib.error import URLError
from werkzeug.exceptions import HTTPException
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError

def load_config():
    if os.getenv('VERCEL'):
        return
    config = Path(__file__).with_name('.env')
    if config.exists():
        for line in config.read_text(encoding='utf-8-sig').splitlines():
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            name, value = line.split('=', 1)
            name, value = name.strip(), value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                value = value[1:-1]
            if name in ('GOOGLE_API_KEY', 'DRIVE_FOLDER_URL', 'DRIVE_FOLDER_ID', 'PORT'):
                os.environ.setdefault(name, value)

def parse_folder_url(value):
    """Accept only Google Drive folder links; never fetch a supplied URL."""
    parsed = urlparse(value.strip())
    if (parsed.scheme != 'https' or parsed.hostname != 'drive.google.com'
            or parsed.username or parsed.password or parsed.port not in (None, 443)):
        raise ValueError('DRIVE_FOLDER_URL에는 https://drive.google.com 폴더 주소를 입력하세요.')
    match = re.fullmatch(r'/drive(?:/u/\d+)?/folders/([A-Za-z0-9_-]{1,200})/?', parsed.path)
    query = parse_qs(parsed.query)
    folder_id = match.group(1) if match else ''
    if not folder_id and parsed.path.rstrip('/') in ('/folderview', '/open'):
        folder_id = query.get('id', [''])[0]
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,200}', folder_id):
        raise ValueError('DRIVE_FOLDER_URL에 파일 주소가 아닌 공유 폴더 주소를 입력하세요.')
    resource_key = query.get('resourcekey', [''])[0]
    if resource_key and not re.fullmatch(r'[A-Za-z0-9_-]{1,200}', resource_key):
        raise ValueError('공유 폴더 주소의 resourcekey 형식이 올바르지 않습니다.')
    return folder_id, resource_key

load_config()
if os.getenv('VERCEL') and (not os.getenv('GOOGLE_API_KEY', '').strip() or not os.getenv('DRIVE_FOLDER_URL', '').strip()):
    raise ValueError('Vercel에서 GOOGLE_API_KEY와 DRIVE_FOLDER_URL 환경변수를 설정하세요.')
KEY = os.getenv('GOOGLE_API_KEY', '').strip()
FOLDER_URL = os.getenv('DRIVE_FOLDER_URL', '').strip()
ROOT_RESOURCE_KEY = ''
if FOLDER_URL:
    ROOT, ROOT_RESOURCE_KEY = parse_folder_url(FOLDER_URL)
else:
    # Keep compatibility with existing installations that used an ID.
    ROOT = os.getenv('DRIVE_FOLDER_ID', '').strip()
    if ROOT and not re.fullmatch(r'[A-Za-z0-9_-]{1,200}', ROOT):
        raise ValueError('DRIVE_FOLDER_ID 형식이 올바르지 않습니다. DRIVE_FOLDER_URL을 사용하세요.')
    if KEY and not ROOT:
        raise ValueError('DRIVE_FOLDER_URL 환경변수에 공유 폴더 주소를 설정하세요.')
    ROOT = ROOT or 'demo-root'
LIVE = bool(KEY)
FOLDER = 'application/vnd.google-apps.folder'
DEMO = [
    dict(id='sample-folder', name='안내 자료', mimeType=FOLDER, parents=[ROOT]),
    dict(id='sample-file', name='시작 안내.txt', mimeType='text/plain', size='120', modifiedTime='2026-10-12T00:00:00Z', parents=[ROOT]),
    dict(id='nested-file', name='폴더 탐색 예제.txt', mimeType='text/plain', size='80', parents=['sample-folder']),
]

def api(path, params):
    params = dict(params, key=KEY)
    headers = {}
    if ROOT_RESOURCE_KEY:
        headers['X-Goog-Drive-Resource-Keys'] = ROOT + '/' + ROOT_RESOURCE_KEY
    with urlopen(Request('https://www.googleapis.com/drive/v3/' + path + '?' + urlencode(params), headers=headers), timeout=30) as response:
        return json.load(response)

def metadata(fid):
    if not re.fullmatch(r'[\w-]{1,200}', fid):
        raise ValueError('잘못된 파일 주소입니다.')
    if not LIVE:
        if fid == ROOT:
            return dict(id=ROOT, name='공유 자료실', mimeType=FOLDER)
        return next((x for x in DEMO if x['id'] == fid), None)
    return api('files/' + fid, dict(fields='id,name,mimeType,parents,webContentLink,webViewLink,exportLinks,capabilities(canDownload)', supportsAllDrives='true'))

def list_children(fid):
    if not LIVE:
        return [dict(x) for x in DEMO if fid in x['parents']]
    params = dict(q=f"'{fid}' in parents and trashed = false", fields='nextPageToken,files(id,name,mimeType,size,capabilities(canDownload))', pageSize=100, orderBy='folder,name', supportsAllDrives='true', includeItemsFromAllDrives='true')
    items = []
    while True:
        result = api('files', params)
        items.extend(result.get('files', []))
        if not result.get('nextPageToken'):
            return items
        params['pageToken'] = result['nextPageToken']


def within_root(fid, path=''):
    # Verify each edge using the parent's actual listing, not files.get.parents.
    ids = path.split('/') if path else [ROOT]
    if (len(ids) > 100 or ids[0] != ROOT or ids[-1] != fid
            or len(set(ids)) != len(ids)
            or any(not re.fullmatch(r'[\w-]{1,200}', x) for x in ids)):
        raise ValueError('폴더 경로가 올바르지 않습니다. 자료실 첫 화면에서 다시 열어 주세요.')
    trail = [dict(id=ROOT, name='자료실', path=ROOT)]
    current = dict(id=ROOT, name='자료실', mimeType=FOLDER)
    for index, child_id in enumerate(ids[1:], start=1):
        if current['mimeType'] != FOLDER:
            raise ValueError('폴더가 아닙니다.')
        current = next((x for x in list_children(ids[index-1]) if x['id'] == child_id), None)
        if current is None:
            raise ValueError('공유 폴더에서 자료를 찾을 수 없습니다. 이동 또는 삭제 여부를 확인하세요.')
        trail.append(dict(id=child_id, name=current['name'], path='/'.join(ids[:index+1])))
    return trail, current

EXPORTS = {
    'application/vnd.google-apps.document': ('application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'docx', 'document'),
    'application/vnd.google-apps.spreadsheet': ('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'xlsx', 'spreadsheets'),
    'application/vnd.google-apps.presentation': ('application/vnd.openxmlformats-officedocument.presentationml.presentation', 'pptx', 'presentation'),
}


def can_open(item):
    mime = item.get('mimeType', '')
    return (mime in EXPORTS or mime in ('application/pdf', 'text/plain', 'text/csv',
            'application/msword', 'application/vnd.ms-excel', 'application/vnd.ms-powerpoint',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'application/vnd.openxmlformats-officedocument.presentationml.presentation')
            or mime.startswith(('image/', 'audio/', 'video/')))


app = Flask(__name__, static_folder=None)
app.json.ensure_ascii = False


@app.after_request
def response_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Cache-Control'] = 'no-store'
    return response


@app.get('/')
def index():
    return Response(Path(__file__).with_name('index.html').read_bytes(), mimetype='text/html')


@app.get('/api/files')
def files():
    fid = request.args.get('folder') or ROOT
    trail, folder = within_root(fid, request.args.get('path', ''))
    if folder['mimeType'] != FOLDER:
        raise ValueError('폴더가 아닙니다.')
    items = list_children(fid)
    for item in items:
        item['path'] = trail[-1]['path'] + '/' + item['id']
        item['canOpen'] = can_open(item)
        item['downloadFormat'] = EXPORTS.get(item['mimeType'], ('', '', ''))[1]
    return jsonify(files=items, breadcrumbs=trail, demo=not LIVE)


@app.get('/open')
def open_file():
    fid = request.args.get('id', '')
    within_root(fid, request.args.get('path', ''))
    item = metadata(fid)
    if not can_open(item):
        raise ValueError('이 파일 형식은 바로열기를 지원하지 않습니다.')
    target = item.get('webViewLink')
    if not target and item['mimeType'] in EXPORTS:
        target = 'https://docs.google.com/' + EXPORTS[item['mimeType']][2] + '/d/' + fid + '/edit'
    return redirect(target or ('https://drive.google.com/file/d/' + fid + '/view'), code=302)


@app.get('/download')
def download():
    fid = request.args.get('id', '')
    within_root(fid, request.args.get('path', ''))
    item = metadata(fid)
    if item['mimeType'] == FOLDER:
        raise ValueError('폴더 전체 다운로드는 지원하지 않습니다.')
    if not LIVE:
        return Response('예시 파일입니다. Google Drive API 연결 후 실제 자료가 표시됩니다.\n',
                        mimetype='text/plain', headers={'Content-Disposition': 'attachment; filename="example.txt"'})
    if item.get('capabilities', {}).get('canDownload') is False:
        raise ValueError('소유자가 다운로드를 허용하지 않은 파일입니다.')
    if item['mimeType'] in EXPORTS:
        mime, extension, editor = EXPORTS[item['mimeType']]
        target = item.get('exportLinks', {}).get(mime)
        if not target:
            target = 'https://docs.google.com/' + editor + '/d/' + fid + '/export?' + urlencode({'format': extension})
    elif item['mimeType'].startswith('application/vnd.google-apps.'):
        raise ValueError('이 Google 파일 형식은 다운로드를 지원하지 않습니다.')
    else:
        target = item.get('webContentLink') or ('https://drive.google.com/uc?' + urlencode({'export': 'download', 'id': fid}))
    return redirect(target, code=302)


@app.errorhandler(ValueError)
def invalid_request(error):
    return jsonify(error=str(error)), 400


@app.errorhandler(HTTPError)
def drive_error(error):
    return jsonify(error=f'Google Drive 접근 실패 ({error.code}). API 활성화와 공유 권한을 확인하세요.'), 502


@app.errorhandler(URLError)
@app.errorhandler(TimeoutError)
def network_error(error):
    return jsonify(error='Drive 연결이 지연되거나 실패했습니다. 잠시 후 다시 시도하세요.'), 503


@app.errorhandler(HTTPException)
def http_error(error):
    return jsonify(error='페이지를 찾을 수 없습니다.' if error.code == 404 else '요청을 처리할 수 없습니다.'), error.code


@app.errorhandler(Exception)
def unexpected_error(error):
    # Avoid logging upstream request URLs that may contain the API key.
    return jsonify(error='요청을 처리할 수 없습니다. 서버 설정을 확인하세요.'), 500


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=int(os.getenv('PORT', '8000')), debug=False)
