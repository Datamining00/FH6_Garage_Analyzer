import difflib
import hashlib
import json
import shutil
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

source = Path(__file__).resolve().parents[1]
repo = source.parents[2]
out = repo / 'artifacts' / 'auto-detection-ui-update'
portable = out / 'FH6 Assistant v1.4 Portable'
with ZipFile(out / 'FH6-Assistant-v1.4-AutoDetection-Portable.zip', 'w', ZIP_DEFLATED) as archive:
    for path in portable.rglob('*'):
        if path.is_file():
            archive.write(path, path.relative_to(out))
changes = []
patches = []
with ZipFile(repo / 'work' / 'auto-detection-ui-base.zip') as base, ZipFile(out / 'source-changes.zip', 'w', ZIP_DEFLATED) as archive:
    names = set(base.namelist())
    for folder in ('fh6garage', 'tests', 'tools'):
        for path in sorted((source / folder).rglob('*.py')):
            relative = path.relative_to(source).as_posix()
            name = 'source-v1.2/' + relative
            old = base.read(name) if name in names else b''
            new = path.read_bytes()
            if old == new:
                continue
            changes.append(relative)
            archive.write(path, name)
            patches.extend(difflib.unified_diff(old.decode('utf8').splitlines(True), new.decode('utf8').splitlines(True),
                fromfile='a/' + name, tofile='b/' + name))
(out / 'source-changes.patch').write_text(''.join(patches), encoding='utf8')
for filename in ('ui-fix-final-regression.log', 'ui-fix-ui.log', 'ui-fix-build-standard.log', 'ui-fix-build-portable.log'):
    shutil.copy2(repo / filename, out / 'validation' / filename)
report = '''# Auto-detection UI update

기준: v1.4-rc1-wheel-morph-w3 / 66d01d0.
기존 auto-detection 실행 파일 내 181개 앱 모듈이 기준 소스와 일치함을 확인했다.
폐기한 startup-records 패치는 포함하지 않았다.

## 변경
- 소울바운드는 자동 감시와 새로고침 변동 집계에서 제외. 구형 이력의 소울바운드도 삭제로 계산하지 않는다. 기존 소울바운드 목록·미리보기·수동 메모리 판정 기능은 유지.
- 숨김 버튼 활성화 OFF 시 버튼은 보이고 클릭만 비활성화.
- 경매장 표시는 썸네일 중앙 상단 Auction 문구로 변경. 다운로드 날짜와 동일한 배경·글자 스타일.
- 설정 문구: 이름이 다른 리버리 중복 백업 허용 / 이름이 같은 리버리 중복 백업 허용.
- 기본값: 자동 감지·날짜·숨김 버튼·잘라내기 비활성화·적용 중 경고 ON. 자동 백업·렌더 캐시·재질 생략·경매장 표시·두 중복 백업 옵션 OFF. CPU 자동.
- 기존에 저장한 설정은 유지한다. 기본값은 저장값이 없는 설정에 적용한다.
- 리버리와 백업 카드 툴팁에 공통의 명시적 배경·문자 색상 적용.
- 메모리 정상 결과를 사용자가 적용하면 자동 새로고침. 거절·불확실·실패 결과는 재스캔하지 않는다.
- 차량 DB 두 소스의 업데이트 완료 후 자동 새로고침. 다른 작업·선택·모달창이 끝날 때까지 대기하며 경로가 바뀌면 취소한다.
- 자동 메모리 스캔은 추가하지 않았다. 완료 후 대기용 타이머는 파일 새로고침을 한 번 실행할 뿐 메모리 스캔을 시작하지 않는다.

## 검증
- Python 3.12.14, 최종 격리 테스트 1,033개 통과. 초기 실패는 변경된 기본값에 의존하던 캐시·잘라내기 검사의 조건을 명시하여 해결했다.
- 임시 파일 기반 일반 리버리 감지 회귀, 소울바운드 부분 파일 무시·기존 이력 호환 검사.
- 실제 앱 패치 전체를 적용한 UI에서 설정·Auction 위치·숨김 비활성화·백업 툴팁 검증. 백업 툴팁 문자색 #303341 확인.
- 모의 메모리 결과 적용/거절/불확실 및 두 DB 업데이트 완료 경로 검증. 실제 게임 메모리나 네트워크 업데이트를 사용하지 않았다.
- 두 빌드의 앱 모듈 각 182개가 수정 소스와 일치. 폐기 패치 모듈 없음.
- 일반판·포터블 각 3회 offscreen 실행 후 정상 종료(코드 0). 임시 LocalAppData 옵션에서 자동 감지를 껐다. 네이티브 Qt 설정은 기존 값을 읽을 수 있으나 게임 파일 스캔·변경은 하지 않았다.
- compileall 통과. 포터블 및 변경 소스 ZIP CRC 확인.

실제 게임의 다운로드·메모리 스캔·온라인 DB 업데이트와 실제 Windows 화면에서의 최종 확인은 사용자 확인 범위다. 이번 작업은 성능 최적화가 아니며 시작 속도 향상을 주장하지 않는다.

## 소스와 배포
이번에 채택한 소스: work/auto-detection-ui-fix/source-v1.2.
루트 source-v1.2에는 폐기한 패치의 미커밋 작업을 그대로 보존했다. 후속 작업은 위 채택 소스를 사용한다.
업데이트 경로: artifacts/auto-detection/FH6 Assistant v1.4.exe.
업데이트 전 배포 폴더: artifacts/auto-detection-before-ui-update.
별도 빌드 원본: artifacts/auto-detection-ui-update.
'''
(out / 'README.md').write_text(report, encoding='utf8')
(repo / 'docs' / 'auto-detection-ui-update-2026-09-11.md').write_text(report, encoding='utf8')
files = [out / 'FH6 Assistant v1.4.exe', portable / 'FH6 Assistant v1.4.exe',
         out / 'FH6-Assistant-v1.4-AutoDetection-Portable.zip', out / 'source-changes.zip']
hashes = {str(p.relative_to(out)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
(out / 'manifest.json').write_text(json.dumps({'base': '66d01d0', 'source': str(source),
    'tests_passed': 1033, 'python': '3.12.14', 'changed_files': changes, 'sha256': hashes}, ensure_ascii=False, indent=2), encoding='utf8')
(out / 'SHA256SUMS.txt').write_text(''.join(f'{digest}  {name}\n' for name, digest in hashes.items()), encoding='utf8')
for path in files:
    if path.suffix == '.zip':
        with ZipFile(path) as archive:
            assert archive.testzip() is None
print('Release packaged and ZIPs verified; changed files:', len(changes))
