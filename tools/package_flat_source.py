"""Create a source ZIP with app.py at its root, retaining development references."""
import hashlib
from pathlib import Path
import tempfile
import zipfile
from fetch_sources import ROOT, prepare
from package import source_files


def main():
    archives = prepare(verify_only=True)
    files = {}
    for path in source_files(archives):
        relative = path.relative_to(ROOT)
        if relative.parts[0] == 'source-v1.2':
            name = Path(*relative.parts[1:]).as_posix()
        else:
            name = 'repository/' + relative.as_posix()
        if name in files:
            raise ValueError(f'Duplicate archive member: {name}')
        files[name] = path.read_bytes()
    files['verified-build-requirements.txt'] = (ROOT / 'verified-build-requirements.txt').read_bytes()
    files['build_exe.ps1'] = b'''$ErrorActionPreference = 'Stop'
$pythonPath = Join-Path $PSScriptRoot '.build-venv\\Scripts\\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    py -3.12 -m venv (Join-Path $PSScriptRoot '.build-venv')
    if ($LASTEXITCODE -ne 0) { throw 'Python environment creation failed.' }
}
& $pythonPath -m pip install -r (Join-Path $PSScriptRoot 'verified-build-requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
& $pythonPath (Join-Path $PSScriptRoot 'repository\\tools\\build.py') --distribution all
if ($LASTEXITCODE -ne 0) { throw 'Build failed.' }
'''
    build = files['repository/tools/build.py'].decode('utf-8-sig')
    build = build.replace('parents[1]', 'parents[2]')
    build = build.replace("'source-v1.2/runtime/", "'runtime/")
    build = build.replace("cwd=ROOT / 'source-v1.2'", 'cwd=ROOT')
    files['repository/tools/build.py'] = build.encode('utf-8')
    files['tools/build_refinement_release.py'] = b'''from pathlib import Path
import runpy
runpy.run_path(str(Path(__file__).resolve().parents[1] / 'repository/tools/build.py'), run_name='__main__')
'''
    # Only repository-location assertions change; application tests are retained.
    substitutions = {
        'tests/test_v1_4_backup_repository.py': [('../tools/', 'repository/tools/')],
        'tests/test_v1_4_private_data_release_contract.py': [('../.gitignore', 'repository/.gitignore'), ('../.github/', 'repository/.github/')],
        'tests/test_wheel_diagnostic_bundle_imports.py': [
            ('parents[2]', 'parents[1]'),
            ('repo / \'docs/history/', 'repo / \'repository/docs/history/'),
            ('shutil.copyfile(repo / relative, target)', "shutil.copyfile(repo / relative.relative_to('source-v1.2'), target)")],
    }
    for name, replacements in substitutions.items():
        text = files[name].decode('utf-8-sig')
        for old, new in replacements:
            if old not in text:
                raise ValueError(f'Expected path missing: {name}: {old}')
            text = text.replace(old, new)
        files[name] = text.encode('utf-8')
    files['README.txt'] = '''FH6 Assistant v1.5 소스
========================

압축을 C:\\FH6src처럼 짧은 경로에 모두 풀어 사용하세요.
app.py, fh6garage, data, icons가 압축 파일 최상위에 있습니다.

실행: Python 3.12 설치 후 PowerShell에서 다음 명령을 실행합니다.
py -3.12 -m venv .build-venv
.\\.build-venv\\Scripts\\python.exe -m pip install -r verified-build-requirements.txt
.\\.build-venv\\Scripts\\python.exe app.py

검사:
.\\.build-venv\\Scripts\\python.exe tools/run_isolated_tests.py

일반판·포터블 빌드:
powershell -ExecutionPolicy Bypass -File build_exe.ps1
결과는 dist에 저장됩니다. 현재 버전 spec은 FH6_Assistant_v1.5*.spec입니다.

FH6 Assistant.vbs 또는 run.bat으로 실행할 수도 있습니다.
기존 실행기는 LocalAppData의 공유 Python 환경을 사용합니다.

licenses: 외부 라이선스 원문
third_party_sources: Qt/PySide6·PyOpenGL·변환기 대응 소스
repository: 원래 저장소 문서·자동화·패키징 도구의 참고 자료
repository 안의 경로 설명은 원래 GitHub 저장소 구조 기준입니다.
이 ZIP의 실행·검사·빌드는 위 명령을 사용하세요.

사용자가 실행한 복원·잘라내기·썸네일 쓰기는 파일을 변경합니다.
설정과 메모 등 사용자 기록은 게임 저장 파일과 별도로 저장됩니다.
'''.encode('utf-8')
    # Keep the original license guidance, with a clear pointer for this layout.
    files['SOURCE_AND_RELINKING.md'] = (
        '> 이 ZIP은 app.py가 최상위에 있는 배포 구조입니다. 실행·재빌드 명령은 README.txt를 사용하세요. 아래 source-v1.2는 이 ZIP의 최상위, 저장소 docs는 repository/docs에 대응합니다.\n\n'.encode('utf-8')
        + files['SOURCE_AND_RELINKING.md'])
    digest_lines = [f'{hashlib.sha256(data).hexdigest()}  {name}\n' for name, data in sorted(files.items())]
    files['FILES_SHA256.txt'] = ''.join(digest_lines).encode('utf-8')
    output = ROOT / 'artifacts/release/FH6-Assistant-v1.5-Source.zip'
    pending = output.with_suffix('.zip.pending')
    with zipfile.ZipFile(pending, 'w', allowZip64=True) as archive:
        for name, data in sorted(files.items()):
            mode = zipfile.ZIP_STORED if name.endswith(('.xz', '.gz', '.zip')) else zipfile.ZIP_DEFLATED
            archive.writestr(name, data, compress_type=mode)
    with zipfile.ZipFile(pending) as archive:
        assert archive.testzip() is None
        assert 'app.py' in archive.namelist()
        assert 'fh6garage/ui.py' in archive.namelist()
        for name, data in files.items():
            assert archive.read(name) == data, name
    pending.replace(output)
    print(output)
    print(hashlib.sha256(output.read_bytes()).hexdigest())


if __name__ == '__main__':
    main()
