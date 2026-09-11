# FH6 v1.4 3D preview audit — 2026-09-11

## 기준과 범위

- 원격 작업 브랜치: `v1.4-rc1-wheel-morph-w3`
- 시작 HEAD: `ecd4ac0f51be9badb3d22e45cf1f866b5775a0bc` (GitHub 원격 재확인 및 fresh clone).
- 시작 HEAD의 관련 Actions 6개 성공, W3 artifact `10154344746` 존재 확인.
- PR #75는 open/draft/unmerged이며 이번 작업 브랜치와 별개의 head를 가리킨다. 병합하지 않았다.
- 게임 ZIP과 세이브는 수정하지 않는다. 테스트/변환 산출물은 별도 작업·임시 캐시에 저장한다.
- UI 기본값 및 `cleanup_ab`/`cleanup_c` 의미는 변경하지 않는다.

## 확정한 타이어 소실 코드 경로

실제 installer는 `tire_preview_integration.py`의 원래 wrapper를 그대로 사용하지 않는다.

```text
_install_native_transform_chain_preview
  material/parser patches
  native_transform_chain_v3
    v2 -> v1 installer
    make_stock_native_tire_convert_wrapper = _make_v5_convert_wrapper
    _try_apply_v5 = _try_apply_v6 (v3 diagnostic ContextVar)
  geometry_cache
  cold_livery -> livery_cache
  tire_cache (legacy.try_apply_stock_native_tire_preview를 감쌈)
  tire provenance -> visibility -> presentation
  global tire installer (위에서 교체한 factory로 integration.convert_vehicle를 감쌈)
```

기존 `_make_v5_convert_wrapper`는 cache가 설치된 public entrypoint를 호출하지 않고 내부 `_try_apply_v5`를 직접 호출했다. 따라서 native tire cache 파일이 배포되어 있어도 production에서는 우회됐다.

동시에 geometry cache hit는 새 `ConversionResult`를 만들면서 `wheel_style_anchors`와 `transform_audit`를 버렸다. v3 타이어 처리는 이 정보를 실제 WheelStyle 위치/림 형상으로 사용한다. 두 번째 실행에서 `validate_converter_transform_inventory`가 실패하면 base GLB로 fallback한다. 체크박스가 ON이어도 base GLB에 고무 타이어가 없으므로 표시할 수 없다.

수정 전 두 개의 실행형 회귀 테스트에서 각각 inventory 소실과 public cache 호출 0회를 확인했다. 수정 후에는 모두 통과했다.

## Stage 1 수행 내용

- 커밋: `85dbc73a2560b90e729f23f071e58dfd88635be8`
- 파일: `geometry_cache_patch.py`, `native_transform_chain_patch.py`, `tire_preview_cache_patch.py`, `test_preview_cache_production_chain.py`.
- geometry manifest에 원본 converter diagnostics를 함께 저장하고 hit에서 복원한다. schema v2로 기존 불완전 manifest를 재사용하지 않는다. 저장은 임시 파일 후 replace한다.
- production wrapper가 public tire-cache entrypoint를 호출하도록 수정했다.
- tire cache가 `converter_diagnostics`를 전달하고 anchor/audit를 키에 포함한다.
- 별도 프로세스 cold/warm 테스트에서 동일한 최종 GLB 경로, caller TemporaryDirectory 정리 후 파일 생존, warm converter/build/attach/merge/bake 호출 0회를 확인했다. 게임 해석 단계는 fixture로 대체한 테스트이며 실제 화면 검증은 아니다.
- 로컬 전체 회귀: 967 PASS. Windows registry 대신 작업 폴더의 Qt INI 설정과 별도 LocalAppData를 사용했다. 초기 sandbox 실행의 설정 저장 오류는 이 격리로 해소했다.
- Actions: transform `34486015671`, production contract `34486015685`, W3 build `34486015817` 성공.
- 배포 artifact: `10155857300` 존재/미만료 확인. 내장 helper SHA-256은 소스의 pinned v16 값과 일치했다.

## Stage 2 캐시 구조 판단

최종 viewer-ready GLB 재사용은 기존 native tire cache가 이미 제공하는 기능이다. 이번에는 새 cache patch를 추가하지 않고 production 연결을 복구했다. warm 경로는 다음과 같다.

```text
asset 선택 -> base geometry key/hit (GLB + converter diagnostics)
 -> tire fingerprint/hit -> persistent final merged+baked GLB
 -> livery cache -> texture 준비 -> parse/materials -> visibility -> scene install
```

캐시 디렉터리를 물리적으로 하나로 합치지는 않았다. base GLB 옆의 material/texture sidecar provenance와 tire 실패 시 fallback을 유지해야 하므로, 측정 없이 base 산출물을 이동·삭제하는 것은 이번 최소 수정 범위에 맞지 않는다. 두 캐시가 함께 차지하는 저장 공간은 남지만 반복 실행의 변환/타이어 생성/병합/bake는 생략된다. DB/spec/asset 변경 확인 비용은 남는다.

## 캐시 목록

`R`은 `%LOCALAPPDATA%/FH6GarageAnalyzer/preview3d_runtime`, `A`는 `%LOCALAPPDATA%/FH6GarageAnalyzer`이다. 생성 시간은 실제 timing으로 측정해야 하며, 아래 비용 설명은 호출되는 작업을 뜻한다.

| 캐시 대상 | 키 / invalidation | 위치·지속성·임시 의존 | 생성 비용 / hit 생략 | viewer 사용·중복/충돌 |
|---|---|---|---|---|
| vehicle index | 정규화 game root; process 종료 시 초기화 | `integration._INDEX_CACHE`, 메모리, TemporaryDirectory 무관 | ZIP 목록/차량 정보 scan / 같은 process scan 생략 | asset 선택에 사용; 같은 process 게임 업데이트 시 자동 invalidation 없음 |
| base geometry | archive path/size/mtime, carbin, converter·normalization·wheel revisions, morph 결과 | `R/geometry_cache_v1`, persistent; 수정 후 schema v2; 임시 무관 | converter, near-LOD, rim 후처리, sidecars / 변환 생략 | tire 입력+fallback; 최종 tire GLB와 body geometry 중복 저장 |
| final native tire GLB | base GLB identity, vehicle archive, wheel DB/spec, tire archive, integration revision, anchor/audit | `R/native_tire_cache_v1`, persistent; 정상 fingerprint 경로는 임시 무관 | tire geometry, attachment, merge, bake / 모두 생략 | 수정 후 production viewer의 최종 경로; base와 독립 삭제 시 miss/rebuild |
| livery sections | source path/size/mtime/SHA-256, resolution, KFPS/runtime revision, game folder | `R/livery_section_cache_v1`, persistent; cold는 임시 PNG를 cache에 복사 | decode, render, PNG encode / hit decode/render 생략 | texture builder가 읽음; cold PNG 일시 중복; game resource 자체의 변경 identity는 키에 없음 |
| wheel SQLite | pinned commit, byte size, Git blob SHA-1, SHA-256 | `R/data/fh6_game_db.sqlite`, persistent | 다운로드·검증 / 정상 파일 재다운로드 생략 | morph 및 tire spec resolve; read-only SQLite |
| wheel DB verification memo | path/size/mtime + pinned hash identity | process set, 임시 무관 | DB 전체 SHA-1/SHA-256 / 같은 process 반복 hash 생략 | 새 process 첫 검증은 다시 수행 |
| native texture payload | payload SHA-256 | caller cache root의 `native_material_textures`, root 수명에 따름 | 게임 payload 탐색/복사 / 동일 payload 저장 생략 | sidecar/material 경로에 따라 사용; root 간 동일 payload 중복 가능 |
| priority texture ZIP inventory | media root 문자열 | LRU 8개, 메모리 | media tree scan / 같은 root scan 생략 | material texture 탐색; process 내 설치 변경 invalidation 없음 |
| parsed save header / SHA | save root namespace + 파일 path/size/mtime/ctime 및 schema | `A/scan_cache`, persistent | header parse·파일 hash / 동일 fingerprint 작업 생략 | 카드/리버리 선택의 상위 시스템; 3D geometry key와 별개 |
| thumbnail image LRU | path/size/mtime | 메모리 LRU | image read/decode / 반복 decode 생략 | 카드 UI; GLB 타이어 소실과 직접 관계 없음 |
| DirectLiveryTextures | persistent cache 없음; controller가 현재 textures 보유 | dialog 메모리 | PNG decode, warp/crop, masks, atlas | UV/eligibility 변경의 `_SceneReloadWorker`는 현재 textures를 그대로 사용 |

geometry/tire cache는 현재 GLB magic/최소 크기 중심의 유효성 검사다. 이는 완전한 mesh/buffer 검증이 아니며 캐시 파일의 임의 손상을 모두 검출한다고 주장하지 않는다. production cache 생성 전에는 attachment 수와 bake geometry를 검증한다. 실제 GLB provenance와 parser primitive 결과는 새 진단에 별도로 남긴다.

## Stage 3 수행 내용

- 커밋: `a4d670e163c6e0b2890b08f00d2b94d2ee6184e2`
- 파일: `kfps_render_backend.py`, `cold_livery_render_fastpath_patch.py`, `__init__.py`, `test_cold_livery_single_decode.py`, W3 workflow.
- 기존 cold wrapper의 metadata decode와 renderer의 실제 decode가 중복됨을 확인했다.
- renderer에 `skip_empty_sections` 옵션을 추가해 이미 decode·raster filtering한 결과에서 빈 section을 건너뛴다. production wrapper가 이를 사용한다.
- `SECTION_NAMES`/`_section_layers` 전역값 임시 변경과 별도 metadata decode를 제거했다. 다른 renderer 전역값까지 thread-safe하다는 뜻은 아니며 병렬 렌더링은 추가하지 않았다.
- sparse/empty/all-section fixture 각각 unwrap/decode/layer-conversion 1회, 빈 PNG 생성 없음 검증. boundary-aware fallback은 기존 판정과 동작을 유지한다.
- 로컬 전체 회귀: 970 PASS. W3 빌드에 전체 regression gate를 추가했다.
- 관련 Actions 6개 성공. W3 build `34486735342`, artifact `10156201991` 존재 확인.

## Stage 4–5 검토 결과

- pinned KFPS `render_typecode_layers_canvas()`의 반환 계약은 PNG bytes이다. 메모리에서 PIL 이미지로 바로 반환하려면 상위 renderer 계약/patch를 수정해야 한다.
- 현재 대형 canvas는 strip 기반 bounded-memory 경로가 있다. 모든 section을 메모리에 유지하는 변경은 peak memory를 악화시킬 수 있으므로 이번에 도입하지 않았다.
- cold source는 cache SHA-256, decoder unwrap, renderer 출력명 digest용으로 반복 읽힌다. fast file identity를 우선 사용하는 구조는 가능하지만 파일 교체/동시 변경을 다루는 검증과 실제 I/O 비중 확인이 필요하다.
- 최종 texture persistent cache는 livery+resolution만으로는 부족하다. vehicle mask ZIP identity, projection/runtime 계약, raster resources 및 배열 shape/dtype 검증을 포함해야 한다. 현재 키의 game resource invalidation부터 확인해야 하므로 추가 cache를 덧붙이지 않았다.
- UV/eligibility만 바꾸는 경로는 이미 기존 in-memory textures를 재사용한다. resolution 변경 또는 새 dialog에서는 atlas/mask 작업이 다시 실행된다.

공개 비교 근거: [pinned KFPS renderer](https://github.com/heyitshestia/kloudys-forza-painter-suite/blob/6f53ca3c584d78659d06d4b4a39561db67d79345/json_preview_renderer.py), [ForzaTechStudio 3D viewer](https://github.com/D3FEKT/ForzaTechStudio/blob/Main/docs/3d-viewer.md). ForzaTechStudio는 별도 viewer 구현이며 이번 앱의 Python wrapper/cache 문제를 증명하는 근거로 사용하지 않았다.

## Stage 6 진단

- 커밋: `2a28f53`.
- `pipeline_diagnostics.py`와 기존 production 단계에 timing 호출을 추가했다. 새 runtime patch를 설치하는 방식이 아니다.
- `%LOCALAPPDATA%/FH6GarageAnalyzer/preview3d_runtime/diagnostics/pipeline/preview_*.json`에 최근 32회 기록. 기존 diagnostic log에는 run ID와 전체 시간이 남는다. release UI는 변경하지 않는다.
- installation, asset/index, geometry lookup, converter/subprocess, wheel DB verify, morph resolve, tire fingerprint/lookup/archive/build/attachment/merge/bake, livery hash/key/lookup/unwrap/decode/layer conversion/render/PNG write/verify, masks/warp/atlas, GLB parse와 material 포함 구간, scene install을 기록한다.
- 최종 selected GLB, geometry/tire cache 상태, tire integration 결과, native mesh/primitive provenance, visibility 선택 상태를 남긴다. scene install은 GUI thread의 별도 trace이며 GLB 경로로 worker trace와 비교할 수 있다.
- timing은 중첩 구간을 포함한다. 모든 elapsed 값을 합산하면 중복 계산되므로 parent 구간과 child 구간을 구분해야 한다. PNG encode는 renderer 내부와 결합되어 section render 구간에 포함된다.
- 로컬 전체 회귀: 972 PASS. thread별 trace 분리와 실패 시 원래 예외 보존 테스트 포함.
- `2a28f53` 관련 Actions 6개 성공, W3 build `34561099598` 성공.
- 후속 상세 측정은 near-LOD, rim/neutral 후처리, native material 준비 및 DDS subprocess 구간을 추가 분리했다. PNG intermediate 정리 후 livery cache hit가 decode/render를 생략하는 회귀도 추가했다. 로컬 전체 회귀 최종 973 PASS.

## 실제 게임 데이터 측정

차량은 설치된 `FER_FXX_05.zip` / Car ID 1006이다. 실제 배포 artifact의 v16 helper를 SHA-256 검증 후 사용했다. 별도 프로세스마다 production과 동일하게 installer를 실행한 뒤 integration을 import했다. 리버리는 지정하지 않은 geometry probe이며 OpenGL 창의 육안 검증은 아니다.

- 수정 전: native tire 적용 성공 후 selected GLB는 caller 임시 폴더에 있었고 cleanup 후 없어졌다. 안정된 geometry key의 다음 hit에서는 `validate_converter_transform_inventory` 오류와 base GLB fallback을 실제 재현했다.
- 수정 후: 첫 실행과 별도 프로세스 재실행 모두 같은 persistent final GLB, native tire primitive 4개, cleanup 후 파일 생존을 확인했다.
- 실제 scene에서 휠/타이어 ON→OFF→ON의 고무 타이어 primitive 수는 **4→0→4**. 표시 triangle 수는 **225806→187876→225806**. optical 이름의 primitive 20개는 visibility 변경 영향을 받지 않았다. 이는 CPU scene/filter 검증이며 실제 GUI 클릭/화면 검증과 구분한다.

검증된 DB를 미리 배치하고 geometry/tire/DDS 캐시가 빈 상태로 실행한 accepted cold trace는 `57537c669da24ef48371f32e302acc97`, 새 프로세스 warm trace는 `3f55c8804298483ebe2256c9200bb485`이다. OS 파일 캐시까지 비운 부팅 직후 측정은 아니다.

| 단계 | Cold | Warm |
|---|---:|---:|
| 전체 geometry probe (리버리/GUI 제외) | 41.472초 | 0.597초 |
| 차량 선택/index | 0.418초 | 0.422초 |
| geometry+tire 준비 | 40.978초 | 약 0.10초 |
| near-LOD 준비 | 1.733초 | 생략 |
| KFPS 차량 converter subprocess | 0.993초 | 생략 |
| native texture 준비 | **37.322초** | 생략 |
| 그중 native texture decoder subprocess | **213회 / 합계 27.677초** | 0회 |
| tire geometry build | 0.066초 | 생략 |
| tire attachment | 0.0003초 | 생략 |
| tire merge | 0.235초 | 생략 |
| tire matrix bake | 0.111초 | 생략 |
| scene parse/provenance 구간 | 0.056초 | 0.059초 |

재질 보고서는 `resolved_all` / `decoded_all`, 213 references / 213 decoded / 0 failures였다. 별도의 정상 cold 실행도 40.197초, texture 준비 36.528초로 확인됐다. **이 차량에서 최초 geometry 준비의 주된 병목은 타이어나 차량 converter가 아니라 native texture 준비다.** decoder subprocess 213회의 합계는 확인했지만 그 내부의 순수 decoding과 process startup 시간을 분리 측정한 것은 아니다.

제외한 측정: DB 네트워크 제한·응답 지연이 포함된 실행, 긴 테스트 경로로 native texture tempfile 생성에 실패한 3.7초 실행. 빠르게 끝났어도 재질 실패가 있는 실행을 성능 개선으로 계산하지 않았다. 초기 probe의 parser import 순서가 production과 다른 결과도 primitive 검증에서 제외했다.

## 실제 runtime 검증과 남은 항목

fixture PASS / Actions PASS / 실제 게임 데이터 parse·filter / OpenGL 화면 육안 검증은 각각 별개다. 사용자의 재현 리버리와 배포본 경로는 아직 특정되지 않았다. 실제 C_livery의 cold/warm 시간, livery가 적용된 최종 화면, 창 닫기/앱 종료 후 사용자 UI 재실행은 남아 있다. 최초 native texture 37초를 줄이는 변경은 아직 하지 않았다.

추가 권고사항: geometry cold 경로는 native DDS decoder의 일괄 호출 가능성을 먼저 검토한다. 리버리는 실제 C_livery cold trace에서 가장 비싼 단계가 확인된 뒤 PNG 전달 또는 최종 texture cache 중 하나만 선택한다. 모든 캐시를 한 번에 통합하지 않는다.
