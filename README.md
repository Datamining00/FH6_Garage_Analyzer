# FH6 Garage Analyzer

FH6의 로컬 저장 폴더를 분석하여 보유 차량, 저장된 리버리, 튜닝 및 제작자 정보를 확인할 수 있는 Windows용 데스크톱 프로그램입니다.

> 이 프로젝트는 비공식 커뮤니티 도구이며 Microsoft, Xbox Game Studios, Playground Games 또는 Forza와 제휴 관계가 없으며 해당 기관의 보증을 받지 않았습니다. 프로그램 사용으로 발생하는 문제나 불이익에 대한 책임은 사용자에게 있습니다.

## 주요 기능

- 보유 차량, 리버리, 튜닝 및 제작자 통계 확인
- 리버리 설명과 제작자 정보 확인
- 튜닝 데이터에 기록된 장착 부품 식별 번호와 세부 설정값을 읽기 전용으로 확인
- 지정한 리버리의 게임 내 위치로 이동 보조

## 파일 변경 범위

일반적인 검색, 정렬, 표시 및 분석 기능은 게임 저장 파일과 섬네일 파일을 변경하지 않습니다. 원, 삼각형, X 및 메모를 이용한 분류 정보는 프로그램의 로컬 설정 파일에만 저장됩니다.

## 설치 및 실행

1. [FH6_Garage_Analyzer_v1.1.zip](https://github.com/Trapdoor00/FH6_Garage_Analyzer/raw/refs/heads/main/releases/FH6_Garage_Analyzer_v1.1.zip)을 내려받습니다.
2. Python 3.12 이상이 설치되어 있는지 확인합니다.
3. 압축을 푼 뒤 `FH6 Garage Analyzer.vbs`를 실행합니다.
4. 최초 실행 시 프로그램 전용 Python 가상 환경과 PySide6가 `%LOCALAPPDATA%\FH6GarageAnalyzer`에 자동으로 준비됩니다.

실행 오류를 확인해야 할 때는 `run.bat`을 실행하십시오.

### 소스 코드로 실행

```powershell
git clone https://github.com/Trapdoor00/FH6_Garage_Analyzer.git
cd FH6_Garage_Analyzer
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

## 기본 사용법

1. `세이브 폴더 선택`을 눌러 FH6의 로컬 저장 경로를 지정합니다.

   경로 예시:

   ```text
   C:\XboxGames\GameSave\pgs\u_XXXXXXXXXXXX_XXXXXX
   ```

   위 경로의 폴더뿐만 아니라 그 아래에 있는 `current`, 숫자로 표시된 버전 폴더 또는 `ContainersRoot` 폴더를 선택할 수 있습니다.

2. 리버리 또는 튜닝 화면에서 검색, 정렬, 필터 및 바둑판형 분류 기능을 사용합니다.
3. 상태 필터 메뉴에서 여러 아이콘을 선택하여 조건을 조합할 수 있습니다.

화면의 그룹 설정은 다음 파일에 저장됩니다.

```text
%LOCALAPPDATA%\FH6GarageAnalyzer\ui_preferences.json
```

메모와 분류 정보는 다음 파일에 저장됩니다.

```text
%LOCALAPPDATA%\FH6GarageAnalyzer\annotations.json
```

## 게임 내 위치 이동 보조

- FH6의 리버리 목록이 첫 번째 항목에 있는 상태를 기준으로 목표 위치까지 필요한 방향키 입력을 전송합니다.
- `삭제하기 위해 이동`을 사용한 항목은 현재 실행 중인 프로그램의 목록에서 제외되며, 이후 위치 계산에도 반영됩니다.
- 실제 삭제를 취소한 경우에는 프로그램에서 목록을 새로 고쳐 위치 계산 정보를 다시 구성해야 합니다.
- 동일 차량 그룹화는 프로그램 화면의 표시 순서에만 적용되며 게임 내 이동에 사용하는 차량 식별 번호 순서는 변경하지 않습니다.

## 시스템 요구 사항

- Windows 11에서 검증됨
- Python 3.12 이상
- PySide6 6.7 이상, 7 미만
- FH6 로컬 저장 폴더에 대한 읽기 권한

## 자료 출처 및 감사

차량 식별 번호 데이터와 튜닝 데이터 구조를 공개한 [HDR](https://gist.github.com/HDR)의 자료를 참고했습니다.

- [Forza Horizon 6 Car Ordinals](https://gist.github.com/HDR/0659d1717bc61504bf83750628963f4f)
- [Forza Horizon 6 Tune Data Structure](https://gist.github.com/HDR/41426137a24ef83b3f391542ce51982d)

유용한 자료를 공개한 HDR에게 감사드립니다.

## 문서

- [변경 이력](https://github.com/Trapdoor00/FH6_Garage_Analyzer/blob/main/CHANGELOG.md)
- [기여 안내](https://github.com/Trapdoor00/FH6_Garage_Analyzer/blob/main/CONTRIBUTING.md)
- [보안 정책](https://github.com/Trapdoor00/FH6_Garage_Analyzer/blob/main/SECURITY.md)

## 라이선스

현재 별도의 오픈 소스 라이선스가 지정되어 있지 않습니다. 라이선스가 추가되기 전까지 저작권법에 따라 모든 권리는 저장소 소유자에게 있습니다.
