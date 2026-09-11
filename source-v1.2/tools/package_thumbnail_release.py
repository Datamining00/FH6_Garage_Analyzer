import difflib, hashlib, json, shutil
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from PyInstaller.archive.readers import CArchiveReader

source = Path(__file__).resolve().parents[1]
repo = source.parents[2]
base = repo/'work/auto-detection-ui-fix/source-v1.2'
out = repo/'artifacts/thumbnail-marking'
checks = {}
for exe, tree in ((repo/'artifacts/auto-detection/FH6 Assistant v1.4.exe', base),
                  (out/'FH6 Assistant v1.4.exe', source),
                  (out/'FH6 Assistant v1.4 Portable/FH6 Assistant v1.4.exe', source)):
    archive = CArchiveReader(str(exe)).open_embedded_archive('PYZ.pyz')
    modules = {}
    for name in archive.toc:
        if not name.startswith('fh6garage.'):
            continue
        path = tree/(name.replace('.', '/')+'.py')
        if not path.exists(): path = path.with_suffix('')/'__init__.py'
        assert path.is_file(), name
        code = archive.extract(name)
        modules[name] = code == compile(path.read_bytes(), code.co_filename, 'exec', dont_inherit=True)
    assert all(modules.values()), [n for n,v in modules.items() if not v]
    checks[str(exe.relative_to(repo/'artifacts'))] = modules
    print(exe.name, len(modules), 'modules match source', flush=True)
(out/'validation/packaged-source-check.json').write_text(json.dumps(checks,indent=2), encoding='utf8')
with ZipFile(out/'FH6-Assistant-v1.4-AutoDetection-Portable.zip', 'w', ZIP_DEFLATED) as archive:
    for path in (out/'FH6 Assistant v1.4 Portable').rglob('*'):
        if path.is_file(): archive.write(path,path.relative_to(out))
changed = []
diff = []
with ZipFile(out/'source-changes.zip', 'w', ZIP_DEFLATED) as archive:
    for folder in ('fh6garage','tests','tools'):
        for path in sorted((source/folder).rglob('*.py')):
            relative = path.relative_to(source)
            original = (base/relative).read_bytes() if (base/relative).exists() else b''
            data = path.read_bytes()
            if data == original: continue
            changed.append(str(relative))
            archive.write(path, Path('source-v1.2')/relative)
            diff.extend(difflib.unified_diff(original.decode('utf8').splitlines(True),data.decode('utf8').splitlines(True),
                fromfile='a/source-v1.2/'+relative.as_posix(),tofile='b/source-v1.2/'+relative.as_posix()))
(out/'source-changes.patch').write_text(''.join(diff),encoding='utf8')
for name in ('thumbnail-final-regression.log','thumbnail-ui.log','thumbnail-build-standard.log','thumbnail-build-portable.log'):
    shutil.copy2(repo/name,out/'validation'/name)
report = '''# 최근 카드·썸네일 표시 업데이트

기준은 직전에 승인한 auto-detection UI update이다. 폐기한 startup-records 패치는 포함하지 않았다.

## 기능
- 최근 변경 창도 일반 리버리 카드 생성 코드를 사용한다. 자동 감지된 추가/중복 카드의 아이콘·정보·동작을 동일하게 제공한다. 삭제 기록도 같은 형태이며 원본이 필요한 버튼은 비활성화한다.
- Auction을 중앙 상단의 대비 높은 흰색/보라색 표시로 개선하고 잠금 아이콘을 옆에 배치한다. 같은 항목의 최근/메인 카드 잠금도 함께 갱신한다.
- 설정 → 표시 → 썸네일에 쓰기. 기본 OFF. ON일 때 경매장 표시 옵션과 리버리 잠금 상태를 실제 썸네일에 반영한다.
- 썸네일에 쓰기 오른쪽에 재적용 버튼을 추가했다. 설정을 저장하고 새로 생성·교체된 썸네일을 다시 연결해 현재 표시 상태를 쓴다. 새 원본 보관과 파일 쓰기가 성공한 항목의 이전 원본은 삭제한다. 다른 항목이 공유하는 원본 또는 실패/파일 없음인 항목의 원본은 유지한다. 이미 표시가 적용된 파일은 기존의 표시 없는 원본을 사용해 중첩을 막는다.
- 일반 리버리는 해당 컨테이너의 bigThumb.webp/BigThumb.webp만 허용한다. 소울바운드는 설정된 CacheThumbnails의 manifest에서 차량 ID와 헤더 토큰이 정확히 연결되는 단일 파일만 허용한다. 다른 차량의 공유 디자인 추정 연결은 쓰기에 사용하지 않는다.
- 앱이 연결하는 기본 경로는 %LOCALAPPDATA%/Packages/Microsoft.ForteBaseGame_8wekyb3d8bbwe/LocalCache/Local/LocalStorage_Cache/CacheThumbnails 이다. 임의의 캐시 전체를 일괄 수정하지 않는다.
- Auction 해제 시 그 문구만 제거하며 잠금이 켜져 있으면 잠금 표시는 유지한다. 잠금 해제도 반영한다. 썸네일에 쓰기 OFF는 기록된 파일을 원복한다.
- 원본은 %LOCALAPPDATA%/FH6GarageAnalyzer/thumbnail_originals 에 해시로 보관한다. 렌더링 캐시와 별개다. 확장자·파일명·이미지 형식·해상도를 유지하며 OFF 복원은 원본 바이트와 일치한다.
- 쓰기 전 원본과 복구 기록을 저장하고 임시 파일을 원자적으로 교체한다. 게임이 교체한 파일, 대응이 모호한 파일, 사용 중이라 쓰기가 거부된 파일은 실패/생략 상세에 표시하고 원본을 보존한다.
- 파일 쓰기는 별도 스레드에서 수행하고 백업·스캔·선택 중에는 기다린다. 새 메모리 스캔 자동 실행은 추가하지 않았다.
- 정상 스캔 완료, 설정 저장, 잠금 변경에 반영한다. 게임이 외부에서 파일을 바꾼 뒤에는 다시 새로고침해야 하며 지속적인 썸네일 폴더 감시를 추가하지 않았다.

## 검증
- Python 3.12.14. 최종 임시 저장소 자동 검사 1,047개 통과.
- 원본 정확한 복원, 반복 쓰기 안정성, 문구만 해제, 게임 파일 교체 충돌, 백업 실패, 쓰기 실패 후 재시도, 중단된 기록 복구, 손상 원본, 형식/확장자 유지, 공유 파일 잠금 충돌, 재시작 후 원복 검사.
- 실제 앱 UI와 임시 manifest 연결을 사용해 최근 카드·삭제 카드 비활성화·잠금 버튼 토글·백그라운드 ON/OFF·원본 미리보기 흐름 확인.
- 일반판·포터블 빌드와 각 3회 offscreen 실행 정상 종료 확인. 시작 측정 로그는 실행 확인용이며 속도 향상을 주장하지 않는다.
- 새 실행 파일의 앱 모듈을 소스와 대조, compileall 및 ZIP CRC 검사.
- 실제 사용자 게임 파일·썸네일에는 쓰지 않았다. 실제 게임에서의 표시 확인은 사용자 확인 범위다.

## 제한과 보존
게임이 이미 메모리에 읽어 둔 썸네일은 파일 수정 즉시 화면에 반영되지 않을 수 있다. JPEG는 표시 적용 중 재인코딩되지만 OFF 원복은 원본 그대로다. 게임이 교체한 파일은 과거 백업으로 덮지 않고 생략하며 보관 원본은 유지한다. 여러 FH6 Assistant 인스턴스의 동시 쓰기는 지원하지 않는다. 게임과의 프로세스 간 잠금 프로토콜은 없으며 쓰기 직전 내용 확인과 원자적 교체로 충돌 가능성을 줄인다.

현재 채택 소스: work/thumbnail-marking/source-v1.2.
직전 소스: work/auto-detection-ui-fix/source-v1.2 (보존).
업데이트 경로: artifacts/auto-detection.
직전 배포 보관: artifacts/auto-detection-before-thumbnail-marking.
별도 빌드 원본: artifacts/thumbnail-marking.
'''
(out/'README.md').write_text(report,encoding='utf8')
(repo/'docs/thumbnail-marking-update.md').write_text(report,encoding='utf8')
paths = [out/'FH6 Assistant v1.4.exe',out/'FH6 Assistant v1.4 Portable/FH6 Assistant v1.4.exe',
    out/'FH6-Assistant-v1.4-AutoDetection-Portable.zip',out/'source-changes.zip']
hashes = {str(path.relative_to(out)):hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
(out/'manifest.json').write_text(json.dumps({'source':str(source),'changed_files':changed,'python':'3.12.14','tests_passed':1047,'sha256':hashes},ensure_ascii=False,indent=2),encoding='utf8')
(out/'SHA256SUMS.txt').write_text(''.join(f'{h}  {p}\n' for p,h in hashes.items()),encoding='utf8')
for path in paths:
    if path.suffix == '.zip':
        with ZipFile(path) as archive: assert archive.testzip() is None
print('Release packaged; ZIP checks passed',flush=True)
