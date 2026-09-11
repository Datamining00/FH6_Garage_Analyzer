# CPU 병렬 처리 확대 검증

## 변경

코드 커밋: `b71d9232f4a0e87d986e89f3678a4063748b769c`.

사용자의 CPU 활용 확대 요청에 따라 native DDS 변환기의 동시 실행 상한을 기존 고정 4개에서 CPU 규모에 따라 자동 결정하도록 바꿨다. `native_material_textures.py`의 계산은 `min(12, max(1, logical_processors * 3 // 4))`이며 CPU 수 조회가 불가능하면 4개 논리 프로세서를 가정해 3개 작업을 사용한다. 이는 CPU 사용률 제한/코어 예약이 아니라 동시 작업 수 제한이다.

검증 PC는 AMD Ryzen 7 9800X3D, 8코어·16논리 프로세서다. 여기서는 12개 helper가 동시에 실행된다. 동일 SHA payload의 직렬 처리, 결과 순서, 오류 격리, 캐시/출력 형식은 이전 구현을 유지한다. 기존 cache를 지우거나 다시 생성할 필요가 없다. livery renderer를 병렬화하지 않았다.

## 실측

동일 FXX payload 213개를 각각 빈 임시 DDS 출력 폴더에 변환했다. 4→8→12→8→4 및 12→16→12 순서로 비교했다. OS 파일 캐시를 비우지 않았고, 측정 중의 프로세스 초기화/백신/시스템 부하가 시간에 영향을 줄 수 있다.

| 동시 helper | DDS 변환 시간 |
|---|---:|
| 4 | 7.640 / 7.943초 |
| 8 | 5.491 / 4.852초 |
| 12 | 4.545 / 3.643 / 3.684초 |
| 16 | 3.558초 |

모든 실행에서 213개 decode 성공, 실패 0개, 기존 DDS SHA-256과 전부 일치했다. 12개 이후 이득이 작아 상한을 12개로 선택했다. 동시에 실행되는 helper가 늘어나는 만큼 순간 메모리/CPU 부하는 높아질 수 있다. 메모리 peak나 CPU 점유율 자체를 계측한 수치는 아니다.

사용자 Car ID 2755 / 제공된 C_livery / 4x / Legacy / UV3의 실제 worker:

| 구간 | 이전 4개 | 새 자동값 12개 |
|---|---:|---:|
| 최초 전체 준비 (OpenGL 표시 제외) | 41.861초 | 35.242초 |
| 그중 native texture 준비 | 21.766초 | 15.915초 |
| 새 프로세스 cache 재사용 전체 준비 | 4.790초 | 4.485초 |

geometry/tire/livery cache가 빈 별도 폴더로 최초 준비를 측정했다. 검증된 DB와 renderer는 미리 준비했다. 전체 최초 준비는 약 6.62초(15.8%) 줄었지만 반복 실행에서는 native decoder를 이미 생략하므로 warm 차이를 이번 병렬화의 개선 효과로 주장하지 않는다.

208개 native texture reference의 status/DDS SHA가 이전 결과와 모두 동일했다 (205개 성공, 기존 unresolved 3개). 최종 리버리 paint SHA도 동일했다. cold/warm 모두 wheel/tire 51→0→51, native rubber 4→0→4, persistent GLB 생존과 원본 C_livery 불변을 확인했다.

## 검증과 다음 병목

- 로컬 전체 회귀 978 PASS. CPU 수별 작업 상한 및 하드 캡 검사를 추가했다.
- 관련 Actions 4개 성공: [native material](https://github.com/Datamining00/FH6_Garage_Analyzer/actions/runs/34573469699), [production contract](https://github.com/Datamining00/FH6_Garage_Analyzer/actions/runs/34573469621), [packaged Paint 자체 검사](https://github.com/Datamining00/FH6_Garage_Analyzer/actions/runs/34573469647), [Standard/Portable build](https://github.com/Datamining00/FH6_Garage_Analyzer/actions/runs/34573469726).
- [배포 artifact 10188856742](https://github.com/Datamining00/FH6_Garage_Analyzer/actions/runs/34573469726/artifacts/10188856742), 213,232,913 bytes, 생성/미만료 확인.
- CPU profile에서 장면 해석 약 3.02초 중 `_direct_uv_mask_evidence`가 약 2.89초를 차지했다. 프로파일러가 추가 비용을 만들므로 이 수치는 일반 실행 시간과 직접 비교하지 않는다.
- UV/mask 검사 1,076회, PIL polygon 호출 449,562회였다. 작은 Python 연산과 raster 호출이 섞여 있으므로 이 부분은 단순 thread 추가보다 동일 계산 중복 여부와 좌표 처리 비용을 먼저 확인해야 한다. 이번에는 판정 로직을 변경하지 않았다.
- 추가 관찰에서 mask 객체·UV/indices dtype·shape·내용이 같은 중복 입력이 593회 확인됐다. 기존 함수를 그대로 호출하고 결과 일치도 검사했으며, 전체 UV 검사 2.305초 중 중복 호출이 1.427초를 차지했다. 캐시를 적용해 줄인 시간이 아니라 중복으로 소비한 시간을 계측한 값이다. 다음 변경은 한 번의 scene parse 안에서 이 결과를 재사용하는 방식이 우선이다.
- 새 배포본의 OpenGL 화면 확인은 별도로 필요하다. PR #75 및 원본 게임/세이브는 변경하지 않았다.
