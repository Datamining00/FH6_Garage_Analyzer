# 사용자 제공 C_livery 실제 검증

## 대상과 방법

- 제공된 `Livery_2755_20260910154936/C_livery`, 124,114 bytes, Car ID 2755 (`POR_Raymond_17`).
- 기본 `ultra4x` (8192×4096), Legacy, UV 3, cleanup A/B 활성·C 비활성으로 측정했다.
- 원본은 읽기 전용. 별도 LocalAppData와 임시 output_root를 사용하고 실행 전후 원본 SHA-256 일치를 확인했다.
- 기존 사용자의 pinned renderer를 테스트 폴더로 복사했다. 런타임 다운로드는 측정에서 제외하고, 동일 런타임을 수정 전/후 양쪽에서 사용했다. OS 파일 캐시를 비우지 않았다.
- 비교 기준 소스는 `ecd4ac0`, 개선 소스는 `5117f8c` (리버리 변경 자체는 `a4d670e`). 각각 별도 프로세스와 빈 section cache를 사용했다. warm도 새 프로세스에서 실행했다.

## 리버리 단독 결과

| 구간 | 수정 전 cold | 수정 후 cold | 수정 후 warm |
|---|---:|---:|---:|
| decode + section render/cache 처리 | 14.187초 | 8.843초 | 0.034초 |
| DirectLiveryTextures 준비 | 1.446초 | 1.538초 | 1.545초 |

8,712개 layer, 실제 section 9개가 생성됐다. 비어 있는 Spoiler/TopWindow는 생략됐다. 4개 raster decal ID (204, 393, 11029, 11030)는 모두 해석됐고 생략된 raster ID는 없다. 생성된 9개 PNG와 최종 paint atlas의 SHA-256은 세 실행 모두 동일했다. paint atlas는 8192×3524다.

기존 decoder warning 893개도 내용까지 동일했다. 경고를 삭제하거나 리소스 identity를 추측해 채우는 변경은 하지 않았다. 이미지가 개선 전과 동일하다는 증거이며 모든 원본 리버리 해석의 정확성을 보증하는 것은 아니다.

수정 후 cold의 구간 기록:

- unwrap 0.0008초, clivery decode 2.104초, layer conversion 2.093초.
- raster resource 준비 0.136초, section render+PNG encode 합계 약 4.50초.
- PNG write 총 약 0.0063초, PNG header verify 총 약 0.0015초. 전체 PNG 크기 2,538,010 bytes.
- PNG encode는 renderer 호출 내부에 포함돼 write 시간과 별개다. disk write 시간이 작다는 사실을 encode 비용이 없다는 의미로 해석하지 않는다.
- cold 반환 PNG는 기존대로 caller 임시 경로이며, 별도의 persistent cache 복사본을 만든다. caller 폴더 정리 후 warm은 그 복사본을 사용하고 decode/render 이벤트가 없다. warm PNG는 cleanup 후에도 생존한다.

## 실제 production worker 전체 경로

`_InitialPipelineWorker.run()` 본문을 실제 차량·리버리로 실행했다. QCoreApplication에서 동기 호출해 준비 경로와 완료 신호를 검사했으며 OpenGL 창 설치/화면 표시 시간은 포함하지 않았다. DB와 renderer는 검증된 복사본을 미리 제공하고 geometry/tire/livery cache는 빈 상태로 시작했다.

| 구간 | cold | 새 프로세스 warm |
|---|---:|---:|
| worker 전체 | 41.861초 | 4.790초 |
| native texture 준비 | 21.766초 | 생략 |
| livery decode+render | 11.086초 | 생략 |
| DirectLiveryTextures | 1.745초 | 1.529초 |
| scene parse/provenance 구간 | 2.856초 | 2.664초 |

단독 리버리 probe와 전체 worker에서 cold 수치가 다르므로 서로 혼합해 가속 비율을 계산하지 않는다. 전체 worker의 수정 전 동등 측정은 수행하지 않았다.

두 실행의 final GLB 경로는 동일하고 임시 폴더 정리 후에도 남았다. wheel/tire ON→OFF→ON에서 wheel/tire primitive 51→0→51, 그중 native rubber tire 4→0→4, 표시 triangle 224024→184384→224024였다. 최종 paint SHA도 단독 측정과 동일했다.

이 차량은 native texture reference 208개 중 205개가 resolve/decode되고 decode 실패는 0개였다. 나머지 symbol texture reference 3개는 `reference_unresolved`이다. 해당 3개를 수정 전 소스의 resolver로 재검사해 같은 결과를 확인했으므로 이번 동시 실행 변경으로 발생한 문제는 아니다.

## 판단과 다음 권고

실제 파일에서도 이중 decode 제거의 효과와 persistent livery cache 재사용을 확인했다. PNG disk write 자체는 약 6ms이므로 이를 먼저 없애는 큰 전달 구조 변경은 이번 측정으로 정당화되지 않는다. 최종 texture cache는 warm에서 약 1.5초를 줄일 여지가 있지만, 먼저 더 큰 scene parse/provenance 2.7초의 세부 비용을 분리하는 편이 타당하다. 이 warm 구간은 리버리가 없는 FXX probe의 parse 약 0.06초와 다른 조건이다.

사용자는 이전 배포본 동작을 확인했다. 이번 `5117f8c`의 새 배포본 GUI 확인은 별도로 남는다. PR #75와 원본 게임/세이브는 변경하지 않았다.
