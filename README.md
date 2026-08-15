# FH6 Garage Analyzer

![FH6 Garage Analyzer banner](docs/banner.svg)

[![Version](https://img.shields.io/badge/version-1.1-6e4bf2)](https://github.com/Trapdoor00/FH6_Garage_Analyzer/releases)
[![Platform](https://img.shields.io/badge/platform-Windows-0078D4)](#system-requirements)
[![Python](https://img.shields.io/badge/python-3.10%2B-3776AB)](https://www.python.org/)
[![Tests](https://github.com/Trapdoor00/FH6_Garage_Analyzer/actions/workflows/tests.yml/badge.svg)](https://github.com/Trapdoor00/FH6_Garage_Analyzer/actions/workflows/tests.yml)

FH6의 로컬 PGS 세이브 폴더를 분석하여 보유 차량, 저장 리버리, 튜닝 및 제작자 정보를 한 화면에서 관리하는 Windows 데스크톱 도구입니다.

> 이 프로젝트는 비공식 커뮤니티 도구이며 Microsoft, Xbox Game Studios, Playground Games 또는 Forza와 제휴하거나 보증받지 않았습니다.

## 주요 기능

- 보유 차량, 리버리, 튜닝 및 제작자 통계
- 리버리·튜닝 전용 2열 바둑판 보기와 모던 스크롤바
- 차량명·제작자·다운로드일 정렬과 250ms 지연 검색
- 동일 차량 그룹화 및 그룹별 표시 개수
- 녹색 원형 체크, 삼각형, X, 메모 분류
- 중복 리버리 필터
- 아이콘 기반 복수 상태 필터
- 리버리 설명·제작자 업로드 날짜 확인
- 튜닝 Data의 장착 부품 ID와 세부 설정값 읽기 전용 보기
- FH6 창 자동 활성화와 인게임 위치 이동 보조
- 선택형 항상 위 표시와 장시간 작업 로딩 화면
- Car ID 데이터베이스 수동 업데이트 및 사용자 오버라이드

## 안전 범위

일반 스캔·검색·정렬·표시와 체크·삼각형·X·메모 분류는 세이브 및 썸네일 파일을 수정하지 않습니다. 분류 상태는 로컬 설정 파일에만 저장됩니다.

## 설치 및 실행

### 권장: 클린 배포본

1. [FH6_Garage_Analyzer_v1.1_clean.zip](releases/FH6_Garage_Analyzer_v1.1_clean.zip)을 받습니다.
2. 쓰기 가능한 일반 폴더에 압축을 풉니다.
3. `FH6 Garage Analyzer.vbs`를 실행합니다.
4. 최초 실행 시 필요한 Python 환경과 PySide6가 `%LOCALAPPDATA%\FH6GarageAnalyzer`에 준비됩니다.

오류를 확인해야 할 때는 CMD 창이 표시되는 `run.bat`을 실행하십시오.

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
2. 대시보드에서 차량·리버리·튜닝 수를 확인합니다.
3. 리버리 또는 튜닝 화면에서 검색, 정렬, 필터와 바둑판 분류 기능을 사용합니다.
4. 상태 필터 메뉴에서는 아이콘을 여러 개 선택하여 조건을 조합할 수 있습니다.

바둑판 화면의 그룹 설정은 다음 파일에 저장됩니다.

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

- Windows 10 또는 Windows 11
- Python 3.10 이상
- PySide6 6.7 이상, 7 미만
- FH6 PGS 세이브 폴더에 대한 읽기 권한

## 개발 및 검증

```powershell
py -3 -m pip install -r requirements.txt pytest
py -3 -m pytest -q
py -3 -m compileall -q app.py fh6garage tests
```

v1.1 기준 자동화 검사 121개가 통과했습니다. 상세 검증 범위는 [VALIDATION.md](VALIDATION.md)를 참고하십시오.

프로그램 아이콘의 SVG·PNG·ICO 시안은 `assets/icons`에 포함되어 있습니다. VBS 자체에는 사용자 아이콘을 내장할 수 없으므로 Windows 바로가기에 ICO를 지정하십시오.

## 문서

- [변경 이력](CHANGELOG.md)
- [v1.1 릴리스 노트](RELEASE_NOTES_v1.1.md)
- [기여 안내](CONTRIBUTING.md)
- [보안 정책](SECURITY.md)

## 라이선스

현재 별도 오픈소스 라이선스가 지정되지 않았습니다. 라이선스가 추가되기 전까지 저작권법상 기본적으로 모든 권리가 저장소 소유자에게 유보됩니다.
