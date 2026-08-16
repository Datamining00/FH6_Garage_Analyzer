# FH6 Garage Analyzer

FH6의 로컬 저장 폴더를 분석하여 보유 차량, 저장된 리버리, 튜닝 및 제작자 정보를 확인할 수 있는 Windows용 데스크톱 프로그램입니다.

> 이 프로젝트는 비공식 커뮤니티 도구이며 Microsoft, Xbox Game Studios, Playground Games 또는 Forza와 제휴 관계가 없으며 해당 기관의 보증을 받지 않았습니다. 프로그램 사용으로 발생하는 문제나 불이익에 대한 책임은 사용자에게 있습니다.

## 주요 기능

* 보유 차량, 리버리, 튜닝 및 제작자 통계 확인
* 리버리 설명과 제작자 정보 확인
* 튜닝 데이터에 기록된 장착 부품 식별 번호와 세부 설정값을 읽기 전용으로 확인
* 지정한 리버리의 게임 내 위치로 이동 보조
* 차량, 리버리 및 튜닝 정보 검색·정렬·필터링
* 원, 삼각형, X 및 메모를 이용한 사용자 분류

## 파일 변경 범위

일반적인 검색, 정렬, 표시 및 분석 기능은 FH6의 게임 저장 파일과 썸네일 파일을 변경하지 않습니다.

프로그램은 FH6의 리버리 및 튜닝 썸네일을 표시 목적으로만 읽으며 원본 썸네일을 수정하지 않습니다.

원, 삼각형, X 및 메모를 이용한 분류 정보는 프로그램의 로컬 설정 파일에만 저장됩니다.

FH6의 실제 게임 저장 데이터와 프로그램의 사용자 설정 데이터는 서로 별도로 관리됩니다.

## 설치 및 실행

1. GitHub Releases에서 `FH6 Assistant v1.1.exe`를 내려받습니다.
2. 내려받은 EXE 파일을 실행합니다.
3. 최초 실행 후 `세이브 폴더 선택`을 눌러 FH6의 로컬 저장 경로를 지정합니다.

v1.1 개선을 통해 별도의 설치 과정은 필요하지 않게 되었습니다.

> 현재 프로그램에는 코드 서명이 적용되어 있지 않으므로 Windows SmartScreen에서 알 수 없는 게시자 또는 보호 경고가 표시될 수 있습니다.

## 기본 사용법

1. `세이브 폴더 선택`을 눌러 FH6의 로컬 저장 경로를 지정합니다.

   경로 예시:

   ```text
   C:\XboxGames\GameSave\pgs\u_XXXXXXXXXXXX_XXXXXX
   ```

   위 경로의 폴더뿐만 아니라 그 아래에 있는 `current`, 숫자로 표시된 버전 폴더 또는 `ContainersRoot` 폴더를 선택할 수 있습니다.

2. 리버리 또는 튜닝 화면에서 검색, 정렬, 필터 및 바둑판형 분류 기능을 사용합니다.

3. 상태 필터 메뉴에서 여러 아이콘을 선택하여 조건을 조합할 수 있습니다.

화면의 그룹 설정 및 표시 관련 설정은 다음 파일에 저장됩니다.

```text
%LOCALAPPDATA%\FH6GarageAnalyzer\ui_preferences.json
```

메모와 분류 정보는 다음 파일에 저장됩니다.

```text
%LOCALAPPDATA%\FH6GarageAnalyzer\annotations.json
```

위 설정 파일은 FH6의 실제 게임 저장 파일과 별도로 관리됩니다.

## 게임 내 위치 이동 보조

* FH6가 전체 화면일 경우 동작이 확인되었습니다.
* FH6의 리버리 목록이 첫 번째 항목에 있는 상태를 기준으로 목표 위치까지 필요한 방향키 입력을 전송합니다.
* `삭제하기 위해 이동`을 사용한 항목은 현재 실행 중인 프로그램의 목록에서 제외되며, 이후 위치 계산에도 반영됩니다.
* 실제 삭제를 취소한 경우에는 프로그램에서 목록을 새로 고쳐 위치 계산 정보를 다시 구성해야 합니다.
* 동일 차량 그룹화는 프로그램 화면의 표시 순서에만 적용되며 게임 내 이동에 사용하는 차량 식별 번호 순서는 변경하지 않습니다.

## 시스템 요구 사항

* Windows 11, 10
* FH6 로컬 저장 폴더에 대한 읽기 권한


## 보안 및 백신 관련 안내

본 프로그램은 PyInstaller를 사용하여 단일 Windows 실행 파일로 패키징되어 있습니다.

디지털 서명이 없어 일부 백신 프로그램 또는 Windows Defender의 머신러닝·휴리스틱 검사에서 PyInstaller 기반 실행 파일이 오탐될 수 있습니다.

virustotal 검사 결과: https://www.virustotal.com/gui/file/12d3483f30df3d2c11358915e5922459b69257fcf90208a4be00488123aca054

SHA-256 파일은 프로그램 실행에 필요한 파일이 아니며 무결성 확인을 위한 선택 사항입니다.


## 자료 출처 및 감사

차량 식별 번호 데이터와 튜닝 데이터 구조를 공개한 [HDR](https://gist.github.com/HDR)의 자료를 참고했습니다.

* [Forza Horizon 6 Car Ordinals](https://gist.github.com/HDR/0659d1717bc61504bf83750628963f4f)
* [Forza Horizon 6 Tune Data Structure](https://gist.github.com/HDR/41426137a24ef83b3f391542ce51982d)

유용한 자료를 공개한 HDR에게 감사드립니다.

본 프로젝트의 개발 과정에서 생성형 AI 도구인 OpenAI ChatGPT의 도움을 받았습니다.

ChatGPT는 코드 작성 및 검토, 오류 분석, 기능 구현 방안 검토와 문서 작성·정리에 보조적으로 활용되었습니다.

## 문서

* [변경 이력](https://github.com/Datamining00/FH6_Garage_Analyzer/blob/main/CHANGELOG.md)
* [기여 안내](https://github.com/Datamining00/FH6_Garage_Analyzer/blob/main/CONTRIBUTING.md)
* [보안 정책](https://github.com/Datamining00/FH6_Garage_Analyzer/blob/main/SECURITY.md)

## 라이선스

현재 별도의 오픈 소스 라이선스가 지정되어 있지 않습니다.

라이선스가 추가되기 전까지 저작권법에 따라 모든 권리는 저장소 소유자에게 있습니다.
