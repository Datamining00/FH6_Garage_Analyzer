import difflib, hashlib, json, shutil
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from PyInstaller.archive.readers import CArchiveReader
source = Path(__file__).resolve().parents[1]
repo = source.parents[2]
base = repo/'work/thumbnail-marking/source-v1.2'
out = repo/'artifacts/thumbnail-placement'
checks = {}
for exe, tree in ((repo/'artifacts/auto-detection/FH6 Assistant v1.4.exe', base),
                  (out/'FH6 Assistant v1.4.exe', source),
                  (out/'FH6 Assistant v1.4 Portable/FH6 Assistant v1.4.exe', source)):
    archive = CArchiveReader(str(exe)).open_embedded_archive('PYZ.pyz')
    modules = {}
    for name in archive.toc:
        if not name.startswith('fh6garage.'): continue
        path = tree/(name.replace('.', '/')+'.py')
        if not path.exists(): path = path.with_suffix('')/'__init__.py'
        code = archive.extract(name)
        modules[name] = code == compile(path.read_bytes(),code.co_filename,'exec',dont_inherit=True)
    assert all(modules.values()), [n for n,v in modules.items() if not v]
    checks[str(exe.relative_to(repo/'artifacts'))] = modules
    print(len(modules),'modules match',flush=True)
(out/'validation/packaged-source-check.json').write_text(json.dumps(checks,indent=2),encoding='utf8')
with ZipFile(out/'FH6-Assistant-v1.4-AutoDetection-Portable.zip','w',ZIP_DEFLATED) as archive:
    for path in (out/'FH6 Assistant v1.4 Portable').rglob('*'):
        if path.is_file(): archive.write(path,path.relative_to(out))
changed, diff = [], []
with ZipFile(out/'source-changes.zip','w',ZIP_DEFLATED) as archive:
    for folder in ('fh6garage','tests','tools'):
        for path in sorted((source/folder).rglob('*.py')):
            rel = path.relative_to(source)
            old = (base/rel).read_bytes() if (base/rel).exists() else b''
            data = path.read_bytes()
            if old == data: continue
            changed.append(str(rel));archive.write(path,Path('source-v1.2')/rel)
            diff.extend(difflib.unified_diff(old.decode('utf8').splitlines(True),data.decode('utf8').splitlines(True),fromfile='a/'+rel.as_posix(),tofile='b/'+rel.as_posix()))
(out/'source-changes.patch').write_text(''.join(diff),encoding='utf8')
for name in ('placement-regression.log','placement-ui.log','placement-build-standard.log','placement-build-portable.log'):
    shutil.copy2(repo/name,out/'validation'/name)
report = '''# 썸네일 위치와 일반 리버리 캐시 연결 수정

직전 thumbnail-marking 배포판을 기준으로 수정했다. 폐기된 startup-records 작업은 포함하지 않는다.

## 실제 데이터 읽기 전용 확인
사용자가 지정한 CacheThumbnails/.manifest와 앱에 저장된 current/ContainersRoot의 header만 읽어 대조했다. 게임 저장/이미지/manifest에 쓰지 않았다.
일반 리버리 791개 중 387개는 차량 ID+헤더 말미 토큰으로 기존 캐시 파일 하나와 연결됐다. 14개는 복수 연결, 나머지는 이 기준의 단일 캐시 연결을 확인하지 못했다. 791개 모두 폴더 썸네일이 존재했다. 소울바운드 47개 중 22개는 단일 캐시 연결이 확인됐고 폴더 썸네일은 없었다. 이 숫자는 확인 당시 상태다.
기존 쓰기 코드는 일반 리버리에 대해 폴더 썸네일만 대상으로 삼았다. 일반 리버리도 캐시 연결이 있다는 근거를 확인했으며, 게임 화면이 해당 캐시를 사용하는 경우 기존 표시가 보이지 않았을 수 있다.

## 변경
- 앱 카드: 다운로드 날짜는 중앙 상단, Auction·잠금 표시는 중앙 하단으로 위치 교환.
- 실제 이미지: Auction·잠금만 하단에 그리며 날짜는 쓰지 않는다.
- 일반·소울바운드 모두 해당 컨테이너의 bigThumb.webp/BigThumb.webp가 있으면 적용한다.
- 두 종류 모두 차량 ID와 헤더 토큰이 정확히 연결된 단일 CacheThumbnails 파일에도 적용한다. 폴더 이미지와 캐시 중 하나만 선택하지 않고 각각 처리한다.
- 일반 리버리에는 잠금 표시만 적용한다. Auction 문구는 소울바운드에만 적용한다.
- 복수 캐시 연결은 캐시 쓰기를 생략하고 상세 내역에 알린다. 이 경우에도 확인된 폴더 썸네일은 처리한다. 서로 다른 잠금/표시 상태가 같은 캐시를 공유하면 그 캐시는 생략한다.
- 원본 백업·확장자/형식/파일명 유지·OFF 원복·재적용·이전 백업 삭제 시점의 보호 동작은 유지한다.
- 기존 상단 표시는 보관 원본에서 새 하단 표시를 다시 생성하여 겹쳐 그리지 않는다. 썸네일에 쓰기를 ON하고 새로고침/설정 저장으로 반영할 수 있다. 게임이 파일을 교체한 경우 재적용을 사용한다.

## 검증
Python 3.12.14, 임시 파일 자동 검사 1,049개 통과. 두 종류의 폴더+캐시 동시 연결, 복수 캐시 생략, 하단 영역만 변경, 실제 Qt 카드 날짜/표시 위치, 원복·재적용 회귀 확인.
일반판·포터블 빌드, 각 3회 offscreen 정상 실행 확인. 임시 LocalAppData와 자동 감지 OFF 옵션을 사용했다. 실제 사용자 이미지 쓰기나 게임 화면 반영 검사는 하지 않았다.
실행 파일 내부 앱 모듈을 현재 소스와 대조했다. compileall, ZIP CRC, 배포 체크섬 확인.

## 산출물과 제한
채택 소스: work/thumbnail-placement/source-v1.2. 직전 소스 work/thumbnail-marking/source-v1.2 보존.
배포 경로 artifacts/auto-detection. 직전 실행 파일은 artifacts/auto-detection-before-thumbnail-placement에 보관.
게임이 이미 읽은 이미지는 파일 수정 즉시 갱신되지 않을 수 있다. 캐시가 없거나 복수로 연결된 항목의 추가 대응은 추정하지 않았다. 실제 게임에서 확인해야 한다.
'''
(out/'README.md').write_text(report,encoding='utf8')
(repo/'docs/thumbnail-placement-update.md').write_text(report,encoding='utf8')
paths = [out/'FH6 Assistant v1.4.exe',out/'FH6 Assistant v1.4 Portable/FH6 Assistant v1.4.exe',out/'FH6-Assistant-v1.4-AutoDetection-Portable.zip',out/'source-changes.zip']
hashes = {str(p.relative_to(out)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
(out/'manifest.json').write_text(json.dumps({'source':str(source),'changed_files':changed,'python':'3.12.14','tests_passed':1049,'sha256':hashes},ensure_ascii=False,indent=2),encoding='utf8')
(out/'SHA256SUMS.txt').write_text(''.join(f'{h}  {p}\n' for p,h in hashes.items()),encoding='utf8')
for p in paths:
    if p.suffix=='.zip':
        with ZipFile(p) as archive: assert archive.testzip() is None
print('Packaged and verified',flush=True)
