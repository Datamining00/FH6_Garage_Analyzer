"""Build v1.5 locally without inheriting unrelated Qt DLL directories."""
import argparse
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--distribution', choices=('all', 'standard', 'portable'), default='all')
    args = parser.parse_args()
    if sys.platform != 'win32':
        parser.error('Windows is required to build Windows distributions.')
    helper = ROOT / 'source-v1.2/runtime/Kfps.ChassisConverter.WheelMorph.exe'
    if not helper.is_file():
        parser.error(f'Required converter is missing: {helper}')
    windows = Path(os.environ.get('WINDIR', 'C:/Windows'))
    env = dict(os.environ)
    env['PATH'] = os.pathsep.join(map(str, (Path(sys.executable).parent,
        Path(sys.base_prefix), windows / 'System32', windows)))
    logs = ROOT / 'artifacts/validation'
    logs.mkdir(parents=True, exist_ok=True)
    for kind, spec in (('standard', 'FH6_Assistant_v1.5.spec'),
                       ('portable', 'FH6_Assistant_v1.5_portable.spec')):
        if args.distribution not in ('all', kind):
            continue
        print(f'Building {kind}; log: {logs / (kind + ".log")}', flush=True)
        with (logs / (kind + '.log')).open('w', encoding='utf-8') as log:
            subprocess.run([sys.executable, '-m', 'PyInstaller', '--clean', '--noconfirm',
                '--distpath', str(ROOT / 'dist'), '--workpath', str(ROOT / 'build' / kind),
                spec], cwd=ROOT / 'source-v1.2', env=env,
                stdout=log, stderr=subprocess.STDOUT, check=True)
        print(f'{kind}: completed', flush=True)

if __name__ == '__main__':
    main()
