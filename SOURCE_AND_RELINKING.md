# 라이브러리 소스 및 교체 안내

FH6 Assistant의 Qt/PySide6 사용은 LGPLv3 허용 모듈을 대상으로 합니다. 라이선스 전문은 licenses/qt의 INDEX.json에서 LGPL-3.0-only.txt 및 GPL-3.0-only.txt 원래 경로를 찾아 열 수 있습니다.

## 대응 소스

일반판 또는 포터블과 같은 배포 페이지에서 FH6-Assistant-v1.5-Full-Source.zip을 함께 제공해야 합니다. 수령인에게 추가 비용이나 별도 승인을 요구하지 않습니다. 소스 ZIP에는 앱 소스, 빌드 spec, 패치 도구와 third_party_sources 폴더의 공식 Qt/PySide6 6.11.2 원본 아카이브가 들어 있습니다. manifest.json의 SHA-256은 공식 다운로드 서버의 체크섬과 대조했습니다. 사용하지 않는 Qt 하위 기능의 소스가 함께 들어 있을 수 있습니다.

Qt/PySide6 자체의 소스는 이번 앱에서 수정하지 않았습니다. 공식 소스:
https://download.qt.io/official_releases/qt/6.11/6.11.2/submodules/
https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.11.2-src/

Qt/PySide6를 소스부터 빌드하는 방법은 각 아카이브의 README와 공식 문서를 참고합니다:
https://doc.qt.io/qt-6/windows-building.html
https://doc.qt.io/qtforpython-6/building_from_source/index.html

## 사용자의 라이브러리 교체와 재구성

앱의 사용 조건은 포함된 LGPL 라이브러리를 수정·교체하거나 그 수정 내용을 디버깅하기 위한 역공학을 제한하지 않습니다. 이 권리 안내는 앱 전체의 일반 재라이선스와 구분됩니다.

- 포터블: 앱을 종료하고 별도 복사본에서 _internal/PySide6 및 관련 Shiboken DLL을 ABI가 호환되는 수정 빌드로 교체할 수 있습니다. 플랫폼·이미지 플러그인도 같은 Qt 빌드와 맞춰야 합니다. DLL 변경 후 다른 ABI/의존성을 쓰면 앱이 실행되지 않을 수 있습니다.
- 일반판: 압축된 단일 실행 파일을 직접 수정할 필요 없이 소스 ZIP으로 다시 빌드할 수 있습니다. 수정한 PySide6/Qt를 설치한 Python 환경에서 아래 spec을 사용합니다. 수정된 라이브러리를 사용자 컴퓨터에서 실행하는 것을 막는 앱 측 서명·해시 검사는 두지 않습니다.
- KFPS WheelMorph helper의 해시 검증은 별도 변환기 무결성 검사이며 Qt/PySide6 교체 검사와 무관합니다.

예시 PowerShell 명령(소스 ZIP을 C:\FH6src 같은 짧은 경로에 푼 뒤 source-v1.2에서 실행):

    py -3.12 -m venv .build-venv
    .\.build-venv\Scripts\python.exe -m pip install -r ..\verified-build-requirements.txt
    # 수정된 PySide6/Qt를 쓰려면 이 시점에 호환되는 수정 패키지를 설치합니다.
    .\.build-venv\Scripts\python.exe -m PyInstaller --clean --noconfirm FH6_Assistant_v1.5.spec
    .\.build-venv\Scripts\python.exe -m PyInstaller --clean --noconfirm FH6_Assistant_v1.5_portable.spec

DLL 탐색 경로에 다른 프로그램의 Qt/ICU가 섞이지 않게 합니다. 원래 검증한 환경은 Python 3.12.14, Windows x64입니다. 이번 검증은 앱 재빌드를 다루며 Qt 전체를 소스부터 재컴파일하거나 모든 ABI 조합을 테스트했다는 의미는 아닙니다.

## 수정된 차량 변환기

원본 커밋과 패치 순서는 docs/history/workflows/validate-v1.4-material-shader-parameters.yml 및 source-v1.2/tools/patch_kfps_*에 있습니다. .NET 9 SDK로 원본 커밋에 해당 패치를 적용해 빌드합니다. 소스 ZIP에 넣은 보조 C# 코드는 이 변환기의 앱 측 변경입니다. 외부 원본의 MIT 고지를 유지해야 합니다.

변환기 원본은 third_party_sources/KFPS-converter-6f53ca3-source.zip에 포함했습니다. 고정 커밋의 66개 원본 파일을 Git blob 해시와 대조했습니다. 별도 작업 폴더에 풀어 tools/patch_kfps_*로 수정합니다. 이 아카이브 자체는 원본이며 앱의 패치가 적용된 것으로 오인하지 않습니다. PyOpenGL 3.1.10 원본 소스와 PyPI 해시 정보도 같은 폴더에 있습니다.
