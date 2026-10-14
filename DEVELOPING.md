# 개발 및 빌드

현재 앱 버전은 **v1.5**입니다. 기존 코드·검사 경로와의 호환성을 위해 소스 폴더 이름 `source-v1.2`를 유지합니다.

| 경로 | 용도 |
|---|---|
| `source-v1.2/app.py`, `fh6garage/` | 현재 앱 진입점·기능 |
| `source-v1.2/tests/` | 임시 저장소 기반 회귀 검사 |
| `source-v1.2/licenses/` | 앱에 포함되는 외부 라이선스 |
| `source-v1.2/third_party_sources/` | 대응 소스 명세·다운로드 위치 |
| `tools/build.py`, `fetch_sources.py`, `package.py` | 현재 빌드·소스 준비·배포 파일 생성 |
| `.github/workflows/ci.yml` | Windows 자동 검사 |
| `docs/history/workflows/` | 이전 버전 작업 기록; 자동 실행되지 않음 |
| `source-v1.1/` | 이전 버전 보존 자료 |
| `dist/`, `build/`, `artifacts/` | 생성물; Git 제외 |

## 환경 준비

Windows x64, Python 3.12를 사용합니다. 기존 배포 검증 환경은 3.12.14이며 의존성 버전은 `verified-build-requirements.txt`에 고정했습니다. 저장소 루트에서 PowerShell로 실행합니다.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r verified-build-requirements.txt
.\.venv\Scripts\python.exe source-v1.2/app.py
```

## 검사

```powershell
.\.venv\Scripts\python.exe source-v1.2/tools/run_isolated_tests.py
git diff --check
```

검사는 임시 사용자 설정과 offscreen Qt 환경을 사용합니다. 실제 게임 저장 데이터·캐시를 수정하거나 게임에 키 입력을 보내는 검사는 자동화에 추가하지 않습니다. 실제 게임 화면, 그래픽 드라이버, Windows 입력기 확인은 별도 사용자 검증입니다.

## 빌드와 배포 파일 생성

```powershell
.\.venv\Scripts\python.exe tools/build.py --distribution all
.\.venv\Scripts\python.exe tools/fetch_sources.py
.\.venv\Scripts\python.exe tools/package.py
```

빌드는 일반판 EXE와 포터블 폴더를 `dist/`에 생성합니다. 소스 준비 명령은 명세에 고정된 외부 소스를 내려받고 해시를 확인합니다(약 700MB). 이미 받은 파일은 검증 후 재사용합니다. `--verify-only`로 다운로드 없이 검사할 수 있습니다.

패키징 결과는 `artifacts/release/`의 일반판 EXE·포터블 ZIP·전체 소스 ZIP 및 해시 목록입니다. 전체 소스 ZIP에는 대응 소스 아카이브를 포함하며, GitHub의 기본 “Source code (zip)”과 다릅니다. Git에는 큰 아카이브 대신 다운로드 명세를 보관합니다. 배포 시 세 파일과 해시·외부 고지를 함께 제공하세요.

현재 자동화는 검사만 수행하며 GitHub Releases에 게시하지 않습니다. 공개 배포 여부와 자료 이용 조건은 [자료 출처 확인](DATA_PROVENANCE_REVIEW.md)을 확인해야 합니다. 라이브러리 교체 안내는 [SOURCE_AND_RELINKING.md](SOURCE_AND_RELINKING.md)에 있습니다.

## 수정 범위

사용자 설정·게임 파일·개인 로그·빌드 환경을 커밋하지 않습니다. `sources/`가 제공된 환경에서는 해당 경로를 읽기 전용으로 취급합니다. 루트의 외부 고지 3개 문서를 바꾸면 `source-v1.2/`의 같은 문서도 함께 갱신해야 합니다. 패키징 단계에서 일치 여부를 검사합니다.

이전 버전의 패치·진단 도구에는 당시 작업 경로가 남아 있을 수 있습니다. 현재 버전의 공식 진입점은 이 문서의 명령입니다.
