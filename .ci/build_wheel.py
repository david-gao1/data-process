"""Build only committed whitelisted sources; local wheel version and manifest bind full SHA."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out',default='dist')
    args = parser.parse_args()
    commit = subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    expected = os.environ.get('CI_COMMIT_SHA')
    if expected and expected != commit:
        raise SystemExit('CI_COMMIT_SHA does not match checkout')
    if subprocess.check_output(['git','status','--porcelain','--untracked-files=normal'],cwd=ROOT).strip():
        raise SystemExit('commit the reviewed changes before producing a commit-bound artifact')
    out = (ROOT/args.out).resolve()
    out.mkdir(parents=True,exist_ok=True)
    if list(out.glob('*.whl')):
        raise SystemExit('use an output directory without existing wheels')
    base = tomllib.loads((ROOT/'pyproject.toml').read_text())['project']['version']
    version = f'{base}+g{commit}'
    info = {'commit_sha':commit,'version':version,'runtime_lock_sha256':sha(ROOT/'uv.lock')}
    with tempfile.TemporaryDirectory(prefix='dp-wheel-source-') as directory:
        stage=Path(directory)
        tracked=subprocess.check_output(['git','ls-tree','-r','--name-only','-z',commit,'--',
                                         'src/data_process','definitions','sources','pyproject.toml','uv.lock'],cwd=ROOT).decode().split('\0')
        for name in filter(None,tracked):
            target=stage/name
            if not target.resolve().is_relative_to(stage):
                raise SystemExit('invalid source path')
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(subprocess.check_output(['git','show',f'{commit}:{name}'],cwd=ROOT))
        pyproject=stage/'pyproject.toml'
        pyproject.write_text(pyproject.read_text().replace(f'version = "{base}"',f'version = "{version}"',1))
        (stage/'src/data_process/_build_info.json').write_text(json.dumps(info,sort_keys=True))
        subprocess.run([sys.executable,'-m','hatchling','build','-t','wheel','-d',str(out)],cwd=stage,check=True)
    wheel,=out.glob('*.whl')
    with zipfile.ZipFile(wheel) as archive:
        names=archive.namelist()
        forbidden=[n for n in names if any(x in n.split('/') for x in ('.data-process','.venv','raw','candidates')) or Path(n).suffix in {'.sqlite','.db','.parquet','.xlsx','.zip','.csv','.pem','.key'}]
        if forbidden: raise SystemExit('unexpected runtime/data files in wheel')
        required={'data_process/resources/definitions/daily_active.sql','data_process/resources/definitions/retail_daily.sql',
                  'data_process/resources/uv.lock','data_process/resources/sources/uci-online-retail.json','data_process/_build_info.json'}
        if not required.issubset(names): raise SystemExit('runtime resources missing from wheel')
    subprocess.run(['uv','export','--frozen','--no-dev','--no-emit-project','--format','requirements-txt',
                    '--output-file',str(out/'runtime-requirements.txt')],cwd=ROOT,check=True,stdout=subprocess.DEVNULL)
    manifest=dict(info,wheel=wheel.name,wheel_sha256=sha(wheel),python=sys.version.split()[0],
                  wheel_members_checked=True,runtime_requirements_sha256=sha(out/'runtime-requirements.txt'))
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2))
    print(json.dumps(manifest,indent=2))


if __name__=='__main__': main()
