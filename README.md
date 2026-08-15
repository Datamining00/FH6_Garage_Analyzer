# FH6 Garage Analyzer

FH6의 로컬 세이브 폴더를 분석하여 보유 차량, 저장 리버리, 튜닝 및 제작자 정보를 확인하는 Windows 데스크톱 도구입니다.

> 이 프로젝트는 비공식 커뮤니티 도구이며 Microsoft, Xbox Game Studios, Playground Games 또는 Forza와 제휴하거나 보증받지 않았습니다. 프로그램 사용으로 인해 발생하는 문제나 불이익에 대한 책임은 사용자에게 있습니다.

## 주요 기능

- 보유 차량, 리버리, 튜닝 및 제작자 통계
- 리버리 설명·제작자 확인
- 튜닝 Data의 장착 부품 ID와 세부 설정값 읽기 전용 보기
- 지정한 리버리 위치로의 이동 보조

## 파일 변경 사항

일반 스캔·검색·정렬·표시와 체크·삼각형·X·메모 분류는 세이브 및 썸네일 파일을 수정하지 않습니다. 분류 상태는 로컬 설정 파일에만 저장됩니다.

## 설치 및 실행

1. [FH6_Garage_Analyzer_v1.1.zip](releases/FH6_Garage_Analyzer_v1.1.zip)을 받습니다.
2. 압축을 푼 뒤 `FH6 Garage Analyzer.vbs`를 실행합니다.
3. 최초 실행 시 필요한 Python 환경과 PySide6가 `%LOCALAPPDATA%\FH6GarageAnalyzer`에 준비됩니다.

오류를 확인해야 할 때는 `run.bat`을 실행하십시오.

### 소스에서 실행

```powershell
git clone https://github.com/Trapdoor00/FH6_Garage_Analyzer.git
cd FH6_Garage_Analyzer
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

## 기본 사용법

1. `세이브 폴더 선택`으로 FH6 PGS 저장 경로를 지정합니다.

   경로 예시:

   ```text
   C:\XboxGames\GameSave\pgs\u_XXXXXXXXXXXX_XXXXXX
   ```

   위 폴더 또는 그 아래의 `current`, 숫자로 된 버전 폴더, `ContainersRoot` 폴더를 선택할 수 있습니다.

2. 리버리 또는 튜닝 화면에서 검색, 정렬, 필터와 바둑판 분류 기능을 사용합니다.
3. 상태 필터 메뉴에서는 아이콘을 여러 개 선택하여 조건을 조합할 수 있습니다.

화면의 그룹 설정은 다음 파일에 저장됩니다.

```text
%LOCALAPPDATA%\FH6GarageAnalyzer\ui_preferences.json
```

메모와 상태 분류는 다음 파일에 저장됩니다.

```text
%LOCALAPPDATA%\FH6GarageAnalyzer\annotations.json
```

## 인게임 이동 보조

- FH6 목록이 첫 번째 항목에 있다고 가정하여 목표까지 필요한 방향키만 전송합니다.
- `삭제하기 위해 이동`한 항목은 현재 세션에서 제외되어 이후 위치 계산에 반영됩니다.
- 실제 삭제를 취소했다면 분석기에서 새로고침하여 세션 목록을 다시 구성해야 합니다.
- 차량 그룹화는 화면 표시 전용이며 인게임 이동의 Car ID 순서를 변경하지 않습니다.

## 시스템 요구사항

- Windows 11에서 검증됨
- Python 3.12 이상
- PySide6 6.7 이상, 7 미만
- FH6 PGS 세이브 폴더에 대한 읽기 권한

## 문서

- [변경 이력](CHANGELOG.md)
- [기여 안내](CONTRIBUTING.md)
- [보안 정책](SECURITY.md)

## 라이선스

현재 별도 오픈소스 라이선스가 지정되지 않았습니다. 라이선스가 추가되기 전까지 저작권법상 기본적으로 모든 권리가 저장소 소유자에게 유보됩니다.
