# Native texture 최초 준비 시간 단축

## 변경과 범위

코드 커밋: `5117f8ca3da0179bbf408b2d6d32e23ffa08015f`.

사용자가 이전 배포본의 동작 확인 후 다음 작업을 요청했다. 기존 측정에서 FXX 최초 geometry 준비 40.978초 중 native texture 준비가 37.322초였다. 서로 다른 swatchbin 213개를 각각 독립된 helper 프로세스로 순차 실행했다.

`native_material_textures.py`에서 독립된 decoder 프로세스만 최대 4개로 겹쳐 실행한다. 동일 payload SHA-256의 항목은 같은 그룹에서 순서대로 처리해 같은 DDS 경로에 동시에 쓰지 않는다. 결과는 원래 reference 순서로 반환한다. ContextVar를 작업별로 복사해 기존 preview timing도 유지한다. renderer, archive resolution, GUI, helper 바이너리/핀, 캐시 키/출력 형식은 변경하지 않는다.

같은 DLL 프로세스 안에서 일괄 decode하는 방식은 helper 계약과 배포 핀을 바꿔야 하므로 이번 최소 수정에서는 적용하지 않았다. 프로세스 수 자체는 여전히 213회이며, 동시 실행의 메모리 비용이 추가된다. 최대 4개로 제한한다.

## 검증

- `test_native_texture_decode_workers.py`: 동시 실행 상한, 같은 payload 중복 쓰기 방지, 원래 결과 순서, trace 전달, warm subprocess 생략, 개별 timeout/오류/SHA 불일치 격리, helper 미제공 검사 3개 PASS.
- 전체 로컬 회귀 977 PASS (Qt 설정과 LocalAppData는 격리).
- native material Actions에 새 검사를 추가했다. W3 앱 빌드의 기존 전체 회귀 gate에서도 실행된다.
- 관련 Actions 4개 모두 성공: [native material](https://github.com/Datamining00/FH6_Garage_Analyzer/actions/runs/34571489361), [production contract](https://github.com/Datamining00/FH6_Garage_Analyzer/actions/runs/34571489389), [packaged Paint 자체 검사](https://github.com/Datamining00/FH6_Garage_Analyzer/actions/runs/34571489362), [Standard/Portable build](https://github.com/Datamining00/FH6_Garage_Analyzer/actions/runs/34571489385).
- [배포 artifact 10188101664](https://github.com/Datamining00/FH6_Garage_Analyzer/actions/runs/34571489385/artifacts/10188101664), 213,236,629 bytes, 생성/미만료 확인.
- 실제 FXX의 기존 추출 payload 213개를 새 임시 DDS 폴더에서 변환했다. 순차/4개 동시/4개 동시 순서로 측정했으며 각 실행은 DDS 캐시가 비어 있었다.

| 구간 | 기존 순차 | 최대 4개 동시 |
|---|---:|---:|
| DDS 213개 변환만 | 27.189초 | 7.767초 / 재측정 7.955초 |
| 전체 geometry+tire 준비 | 이전 측정 40.978초 | 25.514초 |
| 그중 native texture 전체 준비 | 이전 측정 37.322초 | 21.491초 |
| 새 프로세스 geometry+tire 캐시 재사용 | 이전 측정 약 0.10초 | 0.117초 |

단독 변환 결과는 세 실행 모두 213개 성공, 실패 0개, 기존 DDS SHA-256과 213개 모두 일치했다. 전체 경로에서도 타이어 primitive ON/OFF 4/0, caller 임시 폴더 정리 후 persistent GLB 생존을 확인했다. 전체 준비에는 게임 리소스 탐색·읽기·검증이 포함되므로 decoder 단독 시간과 동일한 비율로 줄지는 않는다. 측정값은 이 PC의 FXX 기준이며 리버리/GUI 표시 시간을 제외한다. OS 파일 캐시를 비우지 않았고 전체 순차 값은 이전 검증값이다.

## 남은 확인과 권고

새 배포본 GUI 확인은 아직 필요하다. 제공된 실제 C_livery의 [cold/warm 검증](actual-livery-validation-2026-09-11.md)도 완료했다. 최초 렌더 14.187→8.843초, warm 0.034초였으며 최종 paint 결과는 수정 전과 동일했다. 모든 캐시의 일괄 통합이나 리버리 renderer 병렬화는 이번 변경에 포함하지 않는다.
