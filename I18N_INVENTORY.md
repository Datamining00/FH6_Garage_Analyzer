# FH6 Assistant v1.2 i18n inventory

Generated mechanically from `source-v1.2/**/*.py` by finding Python string literals containing Hangul.
Tests are excluded. Classification is heuristic and must be reviewed before replacing strings.

## Summary

- Hangul string literal occurrences: 419
- Unique file/line/text occurrences: 417
- Files containing Hangul literals: 6

### By category

| Category | Count |
|---|---:|
| user-facing | 123 |
| review | 286 |
| data/pattern | 9 |
| docstring | 1 |

### By file

| File | Count |
|---|---:|
| `fh6garage/ui.py` | 296 |
| `fh6garage/tune_data.py` | 85 |
| `fh6garage/car_db.py` | 18 |
| `fh6garage/game_navigation.py` | 11 |
| `fh6garage/scanner.py` | 6 |
| `fh6garage/parsers.py` | 3 |

## Occurrences

### `fh6garage/car_db.py`

| Line | Category | Literal |
|---:|---|---|
| 99 | review | `기존 업데이트 DB가 내장 DB보다 오래되어 사용하지 않음` |
| 154 | user-facing | `Car ID는 1 이상의 정수여야 합니다.` |
| 156 | user-facing | `의 차량명은 비워둘 수 없습니다.` |
| 166 | user-facing | `Car ID는 1 이상의 정수여야 합니다.` |
| 168 | user-facing | `차량명은 비워둘 수 없습니다.` |
| 248 | user-facing | `차량 DB 응답이 예상 크기(1 MiB)를 초과했습니다.` |
| 253 | user-facing | `차량 DB 다운로드 실패:` |
| 258 | user-facing | `차량 DB JSON 파싱 실패:` |
| 263 | review | `개뿐입니다. 불완전한 응답으로 판단하여 적용하지 않았습니다.` |
| 263 | review | `차량 DB 항목이` |
| 305 | user-facing | `차량 DB 최상위 JSON이 object가 아닙니다.` |
| 322 | review | `동일 Car ID` |
| 322 | review | `에 서로 다른 이름이 존재합니다: '` |
| 374 | user-facing | `업데이트 DB를 읽지 못함:` |
| 377 | user-facing | `업데이트 DB 형식이 잘못됨` |
| 385 | user-facing | `업데이트 DB count 메타데이터가 실제 항목 수와 다름` |
| 387 | user-facing | `업데이트 DB count 메타데이터가 잘못됨` |
| 396 | user-facing | `사용자 override를 읽지 못함:` |

### `fh6garage/game_navigation.py`

| Line | Category | Literal |
|---:|---|---|
| 45 | user-facing | `이동 가능한 항목이 없습니다.` |
| 48 | user-facing | `대상이 현재 인게임 목록에 없습니다.` |
| 151 | user-facing | `실행 중인 Forza Horizon 6 창을 찾지 못했습니다.` |
| 186 | review | `(제목 없음)` |
| 186 | review | `Forza Horizon 6 창을 활성화하지 못했습니다:` |
| 198 | user-facing | `인게임 키 입력은 Windows에서만 지원됩니다.` |
| 212 | user-facing | `활성 창을 확인할 수 없습니다.` |
| 215 | review | `(제목 없음)` |
| 215 | review | `활성 창이 Forza Horizon 6이 아닙니다:` |
| 229 | review | `이동 중 활성 창이 변경되어 남은 입력을 중단했습니다.` |
| 236 | user-facing | `지원하지 않는 이동 키:` |

### `fh6garage/parsers.py`

| Line | Category | Literal |
|---:|---|---|
| 191 | data/pattern | `차고\s*내\s*자동차\s*:\s*([0-9,]+)` |
| 202 | data/pattern | `운전한 시간` |
| 203 | data/pattern | `경험치` |

### `fh6garage/scanner.py`

| Line | Category | Literal |
|---:|---|---|
| 101 | user-facing | `선택한 경로가 폴더가 아닙니다.` |
| 130 | user-facing | `ContainersRoot를 찾지 못했습니다. FH6 세이브 루트/current/버전 폴더 중 하나를 선택하세요.` |
| 165 | user-facing | `: header 없음` |
| 170 | user-facing | `: header 파싱 실패 (` |
| 178 | review | `대신 컨테이너 CarOrdinal` |
| 178 | review | `사용` |

### `fh6garage/tune_data.py`

| Line | Category | Literal |
|---:|---|---|
| 17 | review | `구동계` |
| 17 | review | `엔진` |
| 17 | review | `차체` |
| 18 | review | `모터` |
| 18 | review | `브레이크` |
| 18 | review | `스프링·댐퍼` |
| 19 | review | `전륜 안티롤바` |
| 19 | review | `후륜 안티롤바` |
| 20 | review | `리어 윙` |
| 20 | review | `타이어 컴파운드` |
| 21 | review | `전륜 휠 크기` |
| 21 | review | `후륜 휠 크기` |
| 22 | review | `배기량` |
| 22 | review | `밸브` |
| 22 | review | `캠축` |
| 23 | review | `연료 시스템` |
| 23 | review | `피스톤·압축` |
| 24 | review | `배기` |
| 24 | review | `점화` |
| 24 | review | `흡기` |
| 25 | review | `매니폴드` |
| 25 | review | `플라이휠` |
| 26 | review | `리스트릭터 플레이트` |
| 26 | review | `오일 냉각` |
| 27 | review | `싱글 터보` |
| 27 | review | `트윈 터보` |
| 28 | review | `용적식 슈퍼차저` |
| 28 | review | `쿼드 터보` |
| 29 | review | `원심식 슈퍼차저` |
| 29 | review | `인터쿨러` |
| 30 | review | `변속기` |
| 30 | review | `클러치` |
| 31 | review | `드라이브라인` |
| 31 | review | `디퍼렌셜` |
| 32 | review | `전면 범퍼` |
| 32 | review | `후면 범퍼` |
| 33 | review | `보닛` |
| 33 | review | `사이드 스커트` |
| 34 | review | `전륜 타이어 폭` |
| 34 | review | `후륜 타이어 폭` |
| 35 | review | `경량화` |
| 35 | review | `차체 보강·롤케이지` |
| 36 | review | `모터 부품` |
| 36 | review | `휠 스타일` |
| 37 | review | `과급 방식` |
| 37 | review | `전륜 트랙 폭` |
| 38 | review | `전륜 타이어 편평비` |
| 38 | review | `후륜 트랙 폭` |
| 39 | review | `후륜 타이어 편평비` |
| 39 | review | `후륜 휠 스타일` |
| 43 | review | `전륜 다운포스` |
| 43 | review | `후륜 다운포스` |
| 44 | review | `브레이크 압력` |
| 44 | review | `최종감속비` |
| 45 | review | `브레이크 밸런스` |
| 45 | review | `핸드브레이크 압력` |
| 46 | review | `TCS 슬립 기준` |
| 46 | review | `센터 디퍼렌셜` |
| 47 | review | `전륜 공기압` |
| 47 | review | `전륜 캠버` |
| 48 | review | `전륜 캐스터` |
| 48 | review | `전륜 토` |
| 49 | review | `전륜 스프링` |
| 49 | review | `전륜 안티롤바` |
| 50 | data/pattern | `전륜 범프 강성` |
| 50 | data/pattern | `전륜 차고` |
| 51 | review | `전륜 디퍼렌셜 가속` |
| 51 | review | `전륜 리바운드 강성` |
| 52 | review | `전륜 디퍼렌셜 감속` |
| 52 | review | `후륜 공기압` |
| 53 | review | `후륜 캠버` |
| 53 | review | `후륜 토` |
| 54 | review | `후륜 스프링` |
| 54 | review | `후륜 캐스터` |
| 55 | data/pattern | `후륜 안티롤바` |
| 55 | data/pattern | `후륜 차고` |
| 56 | review | `후륜 리바운드 강성` |
| 56 | review | `후륜 범프 강성` |
| 57 | review | `후륜 디퍼렌셜 가속` |
| 57 | review | `후륜 디퍼렌셜 감속` |
| 58 | review | `단 기어비` |
| 74 | review | `Data 파일 크기가` |
| 74 | review | `바이트입니다. 예상 크기는` |
| 75 | review | `바이트입니다.` |
| 86 | user-facing | `튜닝 값에 NaN 또는 무한대가 포함되어 있습니다.` |

### `fh6garage/ui.py`

| Line | Category | Literal |
|---:|---|---|
| 224 | review | `원 표시` |
| 225 | review | `삼각형 표시` |
| 226 | review | `X 표시` |
| 227 | review | `분류 없음` |
| 228 | review | `메모 있음` |
| 229 | review | `메모 없음` |
| 234 | user-facing | `필터` |
| 238 | user-facing | `상태 필터 · 여러 항목을 동시에 선택할 수 있습니다.` |
| 245 | review | `중복 리버리만` |
| 247 | review | `중복 리버리` |
| 294 | user-facing | `필터` |
| 294 | user-facing | `필터` |
| 401 | user-facing | `처리 중…` |
| 467 | user-facing | `오름차순` |
| 468 | review | `오름차순` |
| 482 | user-facing | `내림차순` |
| 483 | review | `내림차순` |
| 545 | user-facing | `복사` |
| 545 | user-facing | `클릭하여` |
| 559 | review | `클립보드에 복사되었습니다` |
| 682 | review | `처리 중…` |
| 770 | user-facing | `클립보드에 복사되었습니다` |
| 790 | review | `클립보드에 복사되었습니다` |
| 811 | review | `대시보드` |
| 811 | review | `리버리` |
| 811 | review | `튜닝` |
| 822 | user-facing | `항상 위에 표시` |
| 831 | review | `인게임 이동을 시작하면 포르자 화면을 가리지 않도록 분석기 창을 최소화합니다.` |
| 848 | user-facing | `FH6 세이브 루트/current/버전/ContainersRoot 폴더를 선택하세요` |
| 849 | user-facing | `세이브 폴더 선택` |
| 852 | user-facing | `새로고침` |
| 889 | data/pattern | `차고 분석 대시보드` |
| 893 | data/pattern | `차고 차량` |
| 894 | review | `저장 리버리` |
| 895 | review | `저장 튜닝` |
| 902 | user-facing | `차량 DB` |
| 905 | user-facing | `/ 마지막 업데이트: 확인 불가` |
| 911 | user-facing | `업데이트 확인` |
| 913 | user-facing | `차량 DB의 새로운 버전을 확인합니다.` |
| 917 | user-facing | `DB 출처` |
| 921 | user-facing | `차량 DB 원본 페이지를 브라우저에서 엽니다.` |
| 922 | review | `차량 DB 출처 열기` |
| 931 | user-facing | `사용자 차량 이름 지정` |
| 933 | user-facing | `Car ID에 대응하는 차량 이름을 직접 지정하거나 수정합니다.` |
| 954 | user-facing | `차종별 저장 콘텐츠` |
| 960 | user-facing | `제작자별 콘텐츠` |
| 969 | user-facing | `Car ID / 차량명 검색` |
| 984 | review | `리버리` |
| 984 | review | `차량` |
| 984 | review | `튜닝` |
| 990 | review | `리버리` |
| 990 | review | `차량` |
| 990 | review | `튜닝` |
| 1008 | review | `리버리` |
| 1008 | review | `제작자명` |
| 1008 | review | `튜닝` |
| 1008 | review | `합계` |
| 1014 | review | `리버리` |
| 1014 | review | `제작자명` |
| 1014 | review | `튜닝` |
| 1014 | review | `합계` |
| 1034 | user-facing | `차량을 선택하세요` |
| 1042 | user-facing | `저장 리버리` |
| 1049 | review | `리버리 이름` |
| 1049 | review | `제작자` |
| 1052 | user-facing | `저장 튜닝` |
| 1059 | review | `이름` |
| 1059 | review | `제작자` |
| 1059 | review | `크기` |
| 1071 | review | `저장 리버리` |
| 1082 | review | `리버리 이름` |
| 1143 | review | `저장 튜닝` |
| 1156 | review | `튜닝 이름` |
| 1223 | docstring | `Create the common list component used by Livery and Tuning. Visible columns intentionally stay identical: 상태 \| 차량명 \| 제작자 \| 이름 \| 설명 \| 메모 \| 생성일 \| 다운로드일 The future detail co...` |
| 1233 | review | `상태` |
| 1234 | review | `차량명` |
| 1235 | review | `제작자` |
| 1237 | review | `설명` |
| 1238 | review | `메모` |
| 1239 | review | `생성일` |
| 1240 | review | `다운로드일` |
| 1292 | review | `이름 / 제작자 / Car ID / 차량명 / 설명 / 메모 검색` |
| 1309 | user-facing | `정렬:` |
| 1318 | review | `기본` |
| 1319 | review | `브랜드명` |
| 1320 | review | `제작자명` |
| 1321 | review | `다운로드` |
| 1336 | user-facing | `동일 차량끼리 묶기` |
| 1346 | review | `같은 차량의 항목을 모으고 차량명과 현재 표시 개수를 구분 제목으로 표시합니다.` |
| 1386 | user-facing | `FH6 세이브 폴더 선택` |
| 1402 | review | `세이브와 썸네일을 불러오는 중…` |
| 1403 | review | `세이브 스캔 중…` |
| 1433 | review | `완료 —` |
| 1438 | review | `스캔 실패` |
| 1439 | user-facing | `세이브 스캔 실패` |
| 1451 | review | `리버리 목록을 다시 구성하는 중…` |
| 1524 | review | `(제작자 없음)` |
| 1546 | review | `차량 목록을 정렬하는 중…` |
| 1559 | review | `제작자 목록을 정렬하는 중…` |
| 1633 | review | `(제작자 없음)` |
| 1639 | review | `(제작자 없음)` |
| 1639 | review | `(제작자 없음)` |
| 1657 | review | `(제작자 없음)` |
| 1822 | review | `리버리` |
| 1822 | review | `튜닝` |
| 1823 | review | `목록을 정렬하는 중…` |
| 1879 | review | `기본` |
| 1880 | review | `브랜드명` |
| 1881 | review | `제작자명` |
| 1882 | review | `다운로드` |
| 1966 | review | `인게임 이동 대기 중` |
| 1967 | review | `이미 예약된 인게임 이동이 있습니다.` |
| 1975 | review | `인게임 이동 불가` |
| 1976 | review | `현재 스캔 목록에서 대상 위치를 계산할 수 없습니다. 새로고침 후 다시 시도하세요.` |
| 1980 | user-facing | `리버리 위치로 이동` |
| 1986 | review | `(제목 없음)` |
| 2003 | review | `FH6 리버리 목록의 첫 번째 항목을 기준으로 이동합니다. 버튼을 누르면 설정한 대기 시간 후 FH6 창을 활성화하고 방향키 입력을 시작합니다. 리버리를 적용하고 목록으로 돌아오면 해당 항목이 선택됩니다.` |
| 2012 | review | `삭제 위치로 이동한 항목은 현재 목록에서 제외됩니다. 실제 삭제를 취소한 경우 프로그램에서 목록을 새로 고치십시오.` |
| 2028 | user-facing | `실행 설정` |
| 2032 | user-facing | `대기 시간` |
| 2037 | review | `초` |
| 2043 | user-facing | `방향키 간격` |
| 2046 | review | `밀리초` |
| 2052 | user-facing | `FH6 창 자동 활성화` |
| 2057 | review | `대기 시간이 지나면 FH6 창을 찾아 전경으로 전환합니다. 항상 위 표시가 활성화된 경우 이동 전에 이 창을 최소화합니다.` |
| 2066 | user-facing | `삭제 위치로 이동` |
| 2068 | user-facing | `적용 위치로 이동` |
| 2070 | user-facing | `취소` |
| 2093 | user-facing | `인게임 이동 불가` |
| 2104 | review | `초` |
| 2106 | review | `후 FH6 창을 자동 활성화하여 이동합니다` |
| 2108 | review | `후 이동합니다 — 지금 FH6 창으로 전환하세요` |
| 2131 | review | `새로고침으로 예약된 인게임 이동이 취소되었습니다` |
| 2135 | review | `대상이 변경되어 인게임 이동을 취소했습니다` |
| 2144 | user-facing | `인게임 이동 취소` |
| 2145 | review | `FH6 활성 창을 확인하지 못해 키 입력을 취소했습니다` |
| 2156 | review | `회 이동 완료 — 삭제 대상으로 세션 목록에 반영했습니다 (` |
| 2160 | review | `회 이동 완료 — 적용 대상 위치입니다 (` |
| 2194 | user-facing | `상태` |
| 2304 | review | `파일 생성 시각을 확인할 수 없습니다.` |
| 2507 | review | `리버리` |
| 2507 | review | `튜닝` |
| 2522 | review | `개` |
| 2706 | user-facing | `체크 상태 전환` |
| 2707 | review | `리버리` |
| 2707 | review | `튜닝` |
| 2708 | review | `체크 상태` |
| 2727 | user-facing | `삼각형 분류 상태 전환` |
| 2728 | review | `삼각형 분류 상태` |
| 2747 | user-facing | `X 분류 상태 전환` |
| 2748 | review | `X 분류 상태` |
| 2765 | user-facing | `미리보기 크게 보기` |
| 2766 | review | `미리보기 크게 보기` |
| 2781 | review | `클릭하여 메모 수정` |
| 2783 | review | `메모 없음 클릭하여 메모 추가` |
| 2785 | review | `메모` |
| 2800 | user-facing | `인게임에서 이 썸네일 위치로 이동` |
| 2801 | review | `인게임 위치로 이동` |
| 2815 | review | `리버리 설명 및 제작자 업로드 날짜 보기` |
| 2822 | review | `튜닝 Data 세부 정보 보기` |
| 2882 | review | `차량명` |
| 2888 | user-facing | `클릭하여 차량명 복사` |
| 2897 | review | `제목` |
| 2903 | user-facing | `클릭하여 제목 복사` |
| 2908 | review | `제작자명` |
| 2914 | user-facing | `클릭하여 제작자명 복사` |
| 3200 | review | `메모 저장 완료` |
| 3261 | review | `클릭하여 메모 수정` |
| 3264 | review | `메모 없음 클릭하여 메모 추가` |
| 3284 | user-facing | `이 리버리에는 제작자 정보가 없어 일괄 적용할 수 없습니다.` |
| 3284 | user-facing | `제작자 정보 없음` |
| 3287 | user-facing | `메모 없음` |
| 3287 | user-facing | `적용할 메모를 먼저 입력하세요.` |
| 3306 | review | `제작자 리버리에 메모 적용 완료` |
| 3309 | review | `동일 제작자 메모 적용` |
| 3310 | review | `개 기존 메모는 유지되었습니다.` |
| 3310 | review | `개 새로 추가된 메모:` |
| 3310 | review | `대상 리버리:` |
| 3310 | review | `제작자:` |
| 3319 | user-facing | `이 리버리에는 제작자 정보가 없어 일괄 제거할 수 없습니다.` |
| 3319 | user-facing | `제작자 정보 없음` |
| 3332 | user-facing | `제거할 메모 없음` |
| 3332 | user-facing | `제작자의 저장된 메모가 없습니다.` |
| 3337 | review | `동일 제작자 메모 전부 제거` |
| 3338 | review | `개 이 제작자의 모든 리버리 메모를 제거하시겠습니까? 체크 상태는 유지됩니다.` |
| 3338 | review | `메모가 있는 리버리:` |
| 3338 | review | `제작자:` |
| 3351 | review | `개 제거 완료` |
| 3351 | review | `제작자의 메모` |
| 3387 | review | `\n\n클릭하여 메모 수정` |
| 3387 | review | `메모 없음\n\n클릭하여 메모 추가` |
| 3423 | user-facing | `리버리 선택` |
| 3423 | user-facing | `세부 보기에서 리버리를 하나 선택하세요.` |
| 3605 | review | `/ 마지막 업데이트:` |
| 3607 | review | `로컬 DB 다운로드 시각:` |
| 3610 | review | `원본 Last-Modified:` |
| 3615 | user-facing | `/ 마지막 업데이트: 확인 불가` |
| 3617 | review | `아직 수동 차량 DB 업데이트를 적용하지 않았습니다.` |
| 3630 | review | `차량 DB 업데이트` |
| 3631 | review | `공개 GitHub의 FH6 CarOrdinal JSON을 내려받아 LocalAppData의 차량명 캐시만 갱신합니다. 세이브 파일, 세이브 경로, XUID, 리버리/튜닝 데이터는 전송하지 않습니다. 계속하시겠습니까?` |
| 3640 | user-facing | `업데이트 확인 중…` |
| 3641 | review | `차량 DB를 내려받아 갱신하는 중…` |
| 3642 | review | `차량 DB 다운로드 중…` |
| 3663 | review | `차량 DB 업데이트 완료 —` |
| 3666 | review | `차량 DB 업데이트 완료` |
| 3667 | review | `개의 Car ID 매핑을 적용했습니다. 저장 위치:` |
| 3675 | review | `차량 DB 업데이트 실패` |
| 3676 | user-facing | `차량 DB 업데이트 실패` |
| 3684 | user-facing | `차량 DB 업데이트 확인` |
| 3690 | user-facing | `차량명 사용자 오버라이드` |
| 3720 | review | `차량명` |
| 3741 | user-facing | `저장` |
| 3777 | user-facing | `사용자 오버라이드 적용 중` |
| 3779 | user-facing | `더블클릭하여 차량명 수정` |
| 3808 | review | `차량명 확인` |
| 3809 | review | `의 차량명이 비어 있습니다.` |
| 3831 | user-facing | `사용자 오버라이드 적용 중` |
| 3836 | user-facing | `더블클릭하여 차량명 수정` |
| 3848 | review | `오버라이드 저장 실패` |
| 3858 | review | `개` |
| 3858 | review | `사용자 오버라이드 저장 완료 —` |
| 3884 | user-facing | `Car ID / 차량명 검색` |
| 3891 | user-facing | `제작자명 검색` |
| 3909 | review | `차량명:` |
| 3931 | review | `(제작자 없음)` |
| 3942 | user-facing | `제작자명:` |
| 4036 | user-facing | `리버리 정보` |
| 4047 | user-facing | `(제목 없음)` |
| 4047 | user-facing | `리버리:` |
| 4050 | user-facing | `설명` |
| 4054 | review | `설명 없음` |
| 4057 | review | `확인 불가` |
| 4058 | user-facing | `제작자 업로드 날짜:` |
| 4059 | user-facing | `닫기` |
| 4070 | user-facing | `튜닝 세부 정보` |
| 4086 | review | `[기본 정보]` |
| 4087 | review | `(제목 없음)` |
| 4087 | review | `제목:` |
| 4088 | review | `제작자:` |
| 4089 | review | `설명 없음` |
| 4089 | review | `설명:` |
| 4090 | review | `제작자 업로드 날짜:` |
| 4090 | review | `확인 불가` |
| 4094 | review | `Data 파일을 찾을 수 없습니다.` |
| 4094 | review | `[Data 파일]` |
| 4099 | review | `[Data 파일]` |
| 4099 | review | `세부 정보를 읽을 수 없습니다:` |
| 4103 | review | `[Data 파일]` |
| 4104 | review | `형식 버전:` |
| 4105 | review | `잠금 상태:` |
| 4105 | review | `잠기지 않음` |
| 4105 | review | `잠김` |
| 4106 | review | `차량 Ordinal ID:` |
| 4108 | review | `[장착 부품 ID]` |
| 4115 | review | `[세부 튜닝 값]` |
| 4124 | review | `[검증 참고]` |
| 4131 | user-facing | `닫기` |
| 4186 | review | `이미지 없음` |
| 4187 | review | `이 항목의 썸네일을 찾을 수 없습니다.` |
| 4194 | user-facing | `이미지 읽기 실패` |
| 4200 | review | `이미지 읽기 실패` |
| 4201 | review | `썸네일 이미지 형식을 읽을 수 없습니다.` |
| 4234 | user-facing | `축소` |
| 4235 | review | `이미지 축소` |
| 4241 | user-facing | `원본 픽셀 크기` |
| 4244 | user-facing | `맞춤` |
| 4246 | user-facing | `창에 맞추기` |
| 4251 | user-facing | `확대` |
| 4252 | review | `이미지 확대` |
| 4272 | review | `마우스 휠: 확대/축소 · 드래그: 이동 · 더블클릭: 100%` |
| 4337 | review | `리버리 메모` |
| 4339 | review | `튜닝 메모` |
| 4361 | user-facing | `메모` |
| 4366 | user-facing | `메모` |
| 4373 | user-facing | `취소` |
| 4375 | user-facing | `저장` |
| 4443 | user-facing | `체크 상태 전환` |
| 4445 | review | `리버리 체크 상태` |
| 4447 | review | `튜닝 체크 상태` |
| 4479 | user-facing | `삼각형 분류 상태 전환` |
| 4481 | review | `리버리 삼각형 분류 상태` |
| 4483 | review | `튜닝 삼각형 분류 상태` |
| 4514 | review | `\n\n클릭하여 메모 수정` |
| 4514 | review | `메모 없음\n\n클릭하여 메모 추가` |
| 4517 | review | `리버리 메모` |
| 4519 | review | `튜닝 메모` |
| 4548 | user-facing | `X 분류 상태 전환` |
| 4550 | review | `리버리 X 분류 상태` |
| 4550 | review | `튜닝 X 분류 상태` |
| 4676 | review | `클릭하여 메모 수정` |
| 4678 | review | `메모 없음 클릭하여 메모 추가` |
| 4682 | review | `메모 저장 완료` |
| 4721 | user-facing | `미체크` |
| 4721 | user-facing | `체크됨` |
| 4735 | user-facing | `\n\n클릭하여 메모 수정` |
| 4737 | user-facing | `메모 없음\n\n클릭하여 메모 추가` |

