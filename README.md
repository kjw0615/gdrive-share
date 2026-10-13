# Google Drive 자료실 — Flask / Vercel

Python 3.12 이상을 권장합니다. requirements.txt로 Flask를 설치합니다. API 키와 공유 폴더 주소는 환경변수로 설정합니다. 코드에는 실제 폴더 주소나 키를 저장하지 않습니다.

## Google Drive API 키 발급

1. [Google Cloud Console](https://console.cloud.google.com/)에서 프로젝트를 생성하거나 선택합니다.
2. **API 및 서비스 → 라이브러리**에서 **Google Drive API**를 검색하고 **사용**을 클릭합니다.
3. **API 및 서비스 → 사용자 인증 정보 → 사용자 인증 정보 만들기 → API 키**를 선택합니다.
4. 키 설정의 **API 제한사항 → 키 제한**에서 **Google Drive API**만 허용합니다.
5. 서버에서 호출하므로 운영 시 애플리케이션 제한은 서버의 공인 IP 주소로 설정합니다. 웹사이트 HTTP 리퍼러 제한은 이 방식에 맞지 않습니다.
6. Google Drive 폴더의 **공유 → 일반 액세스**를 **링크가 있는 모든 사용자 / 뷰어**로 설정합니다. 하위 파일의 공유 권한도 확인합니다.

API 키는 공개 자료를 읽는 방식입니다. 지정 계정에만 공유된 자료는 이 방식으로 연결되지 않습니다.

## 설정과 실행

이 폴더에서 PowerShell을 열고:

```powershell
Copy-Item .env.example .env  # 처음 설정할 때만 실행
notepad .env
```

`.env`에서 `GOOGLE_API_KEY=` 뒤에 발급받은 키를, `DRIVE_FOLDER_URL=` 뒤에 공유 폴더 주소 전체를 붙여넣고 저장합니다.

```dotenv
GOOGLE_API_KEY=발급받은_API_키
DRIVE_FOLDER_URL=https://drive.google.com/drive/u/0/folders/공유폴더_ID?usp=sharing
PORT=8000
```

폴더를 바꾸려면 DRIVE_FOLDER_URL만 변경한 뒤 서버를 재시작하세요. 코드 수정은 필요 없습니다.
환경변수 DRIVE_FOLDER_URL이 .env에 있는 같은 이름의 값보다 우선합니다. 기존 DRIVE_FOLDER_ID도 호환되지만 DRIVE_FOLDER_URL이 설정되면 URL을 우선합니다.
`/drive/folders/...`, `/drive/u/0/folders/...`, `/folderview?id=...`, `/open?id=...` 형식을 지원합니다. `/open` 링크에는 실제 폴더 ID를 사용해야 합니다.
공유 주소의 resourcekey도 자동 추출하여 서버 요청에 사용합니다.

```powershell
python -m pip install -r requirements.txt
python app.py
```

브라우저에서 http://127.0.0.1:8000 을 엽니다. 종료: Ctrl+C. 설정 변경 후 재시작하세요.
키가 비어 있으면 예시 모드입니다. 키는 Python 서버에서만 사용합니다.
환경 변수로 설정한 값이 .env보다 우선합니다:

```powershell
$env:GOOGLE_API_KEY = '발급받은_API_키'
$env:DRIVE_FOLDER_URL = '복사한_Google_Drive_공유_폴더_주소'
python app.py
```

## 화면과 기능

- 원본 폴더 주소와 원본 폴더 열기 링크를 화면에서 제거했습니다.
- 최상위 폴더명은 '자료실'로 표시하고 하위 폴더 탐색 경로는 유지합니다.
- 게시판 목록, 현재 폴더 파일명 검색, 크기, 바로열기, 다운로드를 제공합니다.
- 다운로드는 Google Drive로 이동합니다. Google Docs는 DOCX, Sheets는 XLSX, Slides는 PPTX로 내보냅니다.
- 원본 폴더 링크를 숨겨도 공유 권한은 바뀌지 않으며 다운로드 시 개별 파일 주소로 이동합니다.
- .env 파일에는 실제 키가 있으므로 공유하거나 배포 압축파일에 넣지 마세요. .gitignore로 버전 관리에서 제외했습니다.

## 오류와 범위

400: API 키 또는 폴더 ID 확인. 403: API 활성화, 키의 API/IP 제한, 공유 권한, 할당량 확인. 404: 폴더 ID와 공개 공유 권한 확인.
폴더 ZIP 다운로드와 전체 하위 폴더 검색을 지원합니다. 바로가기는 자동으로 따라가지 않습니다.
로컬 실행은 이 컴퓨터에서만 접속됩니다. Vercel에서는 플랫폼이 Flask 앱을 실행하고 HTTPS를 제공합니다.

공식 안내: [인증 정보 생성](https://developers.google.com/workspace/guides/create-credentials), [파일 검색](https://developers.google.com/workspace/drive/api/guides/search-files).

## 하위 폴더 접근 오류 수정

상위 폴더 메타데이터 대신 부모 폴더 목록을 조회하여 경로의 각 항목을 검증합니다. API 응답에 parents가 없어도 탐색과 다운로드가 가능합니다.
업데이트 시 app.py와 index.html을 함께 교체하고 기존 .env의 API 키는 유지하고 DRIVE_FOLDER_URL 항목에 공유 폴더 주소를 추가하세요. 서버를 재시작한 뒤 주소의 # 뒤 경로를 지우고 자료실 첫 화면을 새로고침하세요. 이전 버전에서 복사한 하위 폴더 주소는 새 경로 형식과 호환되지 않습니다.

폴더 변경 후 브라우저 주소의 # 뒤 기존 탐색 경로를 지우고 첫 화면에서 다시 시작하세요.

## Vercel 배포

기존 ThreadingHTTPServer 대신 Vercel이 자동 인식하는 `app.py`의 `app = Flask(...)`를 사용합니다. 구형 builds/rewrites 설정은 필요 없습니다.

1. 이 폴더의 배포 파일을 Git 저장소에 올립니다. 실제 .env와 .venv는 제외하세요.
2. Vercel에서 저장소를 Import합니다. **Root Directory**는 app.py와 requirements.txt가 있는 폴더로 선택합니다.
3. Framework Preset이 **Flask**로 감지되는지 확인합니다. 별도 Build Command나 Output Directory를 지정하지 않습니다.
4. **Settings → Environment Variables**에 아래 두 값을 등록합니다. 사용할 Production / Preview 환경 모두 설정하세요.

| 변수 | 값 |
| --- | --- |
| GOOGLE_API_KEY | Google Drive API 키 |
| DRIVE_FOLDER_URL | 공유 폴더 주소 전체 |

5. Deploy합니다. 이후 환경변수나 폴더 주소를 변경하면 **Redeploy**해야 반영됩니다.
6. 배포 주소에서 첫 목록 → 하위 폴더 → 다운로드 순서로 확인합니다.

Vercel에서는 .env를 읽지 않으며 두 환경변수가 없으면 시작 시 설정 오류를 표시합니다. 로컬에서는 기존 .env 방식과 예시 모드를 유지합니다.

`vercel.json`은 앱의 최대 실행 시간을 60초로 설정합니다. 폴더가 매우 깊거나 파일이 많아 조회가 길어지면 시간 제한에 걸릴 수 있습니다. 다운로드는 Drive로 이동하므로 파일 본문을 Vercel을 통해 전송하지 않습니다.

Google API 키의 IP 제한을 로컬 공인 IP로 설정했다면 Vercel 호출은 거부될 수 있습니다. Vercel 배포 환경의 외부 통신 IP 정책에 맞춰 제한을 조정하세요. 웹사이트 리퍼러 제한은 서버 호출에 맞지 않습니다. API 제한은 Google Drive API로 유지하세요.

배포 파일: app.py, index.html, requirements.txt, vercel.json, .gitignore, .vercelignore, .env.example, README.md.

공식 문서: [Flask on Vercel](https://vercel.com/docs/frameworks/backend/flask).
실제 Vercel 배포는 수행하지 않았습니다. Flask 테스트 클라이언트로 엔드포인트를 검증합니다.

## 파일 버튼과 아이콘

- 수정일 열은 표시하지 않습니다.
- Google Docs/Sheets/Slides, PDF, 이미지, 오디오/동영상, 주요 Office 문서와 일반 텍스트는 바로열기를 새 탭으로 제공합니다. Drive 미리보기 지원 여부는 실제 파일 형식과 권한에 따라 달라집니다.
- ZIP, 실행 파일 등 그 외 파일에는 다운로드만 표시합니다.
- Google 문서는 편집기 열기와 파일 내보내기를 구분합니다. 다운로드 제한 자료는 다운로드 버튼을 비활성화합니다.
- PDF, Word, Excel, PowerPoint, 이미지, 압축 파일 등은 색상과 형식명이 있는 SVG 아이콘으로 구분합니다. 외부 이미지 서비스는 사용하지 않습니다.
- 작업 위치: C:\Users\admin\Desktop\web. Vercel에는 변경한 파일을 반영하여 재배포하세요.

## 반응형 디자인

DESIGN-supabase.md의 흰 배경, 근검정 텍스트, 회색 테두리, 에메랄드 포인트를 참고했습니다. 파일 형식 아이콘의 색상은 구분을 위해 유지합니다.
PC에서는 표, 768px 미만에서는 카드 형태의 목록으로 표시합니다. 제목과 여백은 화면 크기에 맞춰 조정되고 긴 파일명은 줄바꿈합니다. 모바일 버튼은 최소 44px 높이입니다.
버튼 화살표를 제거하고 푸터에 현재 연도와 '자료의 저작권은 각 권리자에게 있습니다.' 문구를 표시합니다.

## JW Studio 브랜드 및 하위 폴더 검색

상단 로고, 푸터 심볼, 탭 파비콘은 public/ 폴더의 제공받은 PNG를 사용합니다. public/ 폴더도 Git에 올려야 Vercel 배포에 포함됩니다. 로컬 Flask에서도 같은 주소로 이미지를 제공합니다.
검색창은 현재 및 모든 하위 폴더의 파일명/폴더명을 검색합니다. 결과에 위치를 표시하고 검색 결과에서 열기/다운로드/폴더 이동을 지원합니다. 검색어를 지우면 현재 폴더 목록으로 돌아갑니다.
Vercel 실행 시간에 맞춰 한번에 API 목록 4페이지를 조회하고 서명된 검색 토큰으로 이어서 조회합니다. 검색어 변경 시 이전 요청을 취소합니다. 매우 큰 폴더는 검색에 시간이 걸릴 수 있으며 전체 완료 전에는 '검색 중'으로 표시됩니다. 바로가기는 검색 대상 폴더로 따라가지 않습니다.
파일 아이콘은 기존 30×36px에서 24×29px로 축소했습니다.

## 선택 ZIP 다운로드와 테마

파일/폴더 앞 체크박스로 여러 항목을 선택하고 선택 다운로드를 누릅니다. 전체 선택은 현재 표시된 항목에 적용됩니다. 폴더 이동이나 검색 중에도 선택은 유지되고 선택 해제로 모두 지울 수 있습니다.
폴더 하나는 폴더이름.zip, 여러 항목은 JWStudio_YYYYMMDD_HHMMSS_8자리랜덤.zip으로 저장합니다. 시간은 한국 시간입니다. 폴더 내부 구조와 빈 폴더를 보존하고 상위 폴더와 내부 파일을 함께 선택하면 중복을 제외합니다. 이름이 같은 항목은 번호를 붙입니다.
Google 문서는 DOCX/XLSX/PPTX로 내보내어 포함합니다. 다운로드 제한 파일이나 지원하지 않는 Google 파일 형식은 오류를 표시하며 조용히 누락시키지 않습니다.
ZIP은 fflate 0.8.3을 사용하여 브라우저에서 압축합니다. public/fflate.min.js와 라이선스 파일을 함께 배포하세요. 파일은 서버의 스트리밍 API를 통해 차례대로 받고, 서버에 ZIP을 보관하지 않습니다.
브라우저 메모리 사용을 고려해 원본 데이터 합계는 한번에 256MB까지 지원합니다. Google 문서 API 내보내기는 10MB 제한이 있고, 개별 파일 전송은 Vercel의 함수 실행 시간 제한을 따릅니다. 큰 항목은 나누어 다운로드하세요. 실제 Vercel 대용량 전송은 별도 확인이 필요합니다.
오른쪽 위 일반모드/다크모드 버튼으로 전환하며 선택한 테마는 브라우저에 저장됩니다. 처음 방문하면 다크모드로 시작합니다. 이후에는 직접 선택한 모드를 기억합니다.

## 자료 탐색과 다운로드 상태

파일 / 폴더명과 크기 컬럼 제목을 눌러 오름/내림차순 정렬합니다. 파일 종류 정렬은 제거했습니다. 폴더는 먼저 표시하고 용량이 없는 문서는 크기 정렬의 뒤에 표시합니다. 유형 필터는 검색 결과에도 적용되며 전체 선택은 필터 후 화면에 표시된 항목만 선택합니다.
검색 결과의 일치 문자열을 강조하고 위치 표시 버튼으로 해당 부모 폴더로 이동합니다. 목록/카드 보기는 브라우저에 저장됩니다.
선택 요약에 파일/폴더 개수, 확인된 파일 용량, 크기 미확인 항목과 중복 제외 여부를 표시합니다. 선택 항목의 개수와 용량 요약을 표시합니다. 폴더 내부 및 Google 문서의 실제 용량은 수신 전에 정확히 알 수 없습니다.
일반 파일 다운로드도 브라우저에서 진행 상태와 취소를 지원하며 Google 문서는 내보낸 파일로 저장됩니다. 확인된 크기가 256MB를 넘는 일반 파일은 기존 Google Drive 직접 다운로드를 사용합니다.
ZIP과 일반 파일 수신 중 수신 바이트와 현재 파일을 표시합니다. 전체 용량이 알려졌을 때 수신 퍼센트를, 알 수 없을 때 진행 중 표시를 사용합니다. 폴더 확인 및 ZIP 압축 단계도 별도로 표시합니다. 취소는 네트워크 요청 또는 압축 작업을 중단하며 미완성 파일을 저장하지 않습니다. 브라우저 저장을 시작한 뒤에는 브라우저 다운로드 화면에서 취소해야 합니다.

파일 유형 필터는 검색 입력창 옆에 배치합니다. 모바일 및 카드 보기에서도 이름/크기 컬럼의 정렬 버튼을 제공합니다.
