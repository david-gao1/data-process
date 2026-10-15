"""Offline installed-package acceptance: fixed synthetic inputs, no resident services."""
import argparse
import csv
import importlib.metadata
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from .core import ASSET_ROOT, Platform, demo_csv


def run(home):
    results = []
    for product in ('daily_active', 'retail_daily'):
        p = Platform(Path(home) / product)
        p.init()
        day = '2026-10-14'
        source = p.home / 'input.csv'
        if product == 'daily_active':
            demo_csv(source, day)
        else:
            with source.open('w', newline='') as stream:
                writer = csv.writer(stream)
                writer.writerow(['business_date','country','line_type','amount_pence','source_row'])
                writer.writerows([[day,'United Kingdom','sale',1250,2],[day,'United Kingdom','refund',250,3]])
        release = p.release(ASSET_ROOT / 'definitions' / ('daily_active.sql' if product == 'daily_active' else 'retail_daily.sql'), product)
        ready = p.ready(day, source)
        run_id = p.submit(release, ready, day, key='fixed-offline-smoke')
        assert p.submit(release, ready, day, key='fixed-offline-smoke') == run_id
        child = subprocess.run([sys.executable,'-I','-m','data_process.cli','--home',str(p.home),'worker','--once'],
                               cwd=home, text=True, capture_output=True, timeout=30)
        if child.returncode != 0 or p.run(run_id)['state'] != 'SUCCEEDED':
            raise RuntimeError(f'{product} worker smoke failed; return code {child.returncode}')
        assert p.trend(day,1)['rows'] == []
        p.publish(run_id,None,'offline-smoke','fixed fixture verified')
        rows = p.trend(day,1)['rows']
        if product == 'daily_active':
            assert {r['province']:r['active_users'] for r in rows} == {'北京':3,'上海':4,'广东':5}
        else:
            assert len(rows)==1 and rows[0]['net_sales_pence']==1000 and rows[0]['refund_pence']==250
        p.publish(run_id,None,'offline-smoke','idempotence')
        assert len(p.audit()) == 1 and p.check()['integrity'] == 'ok'
        results.append({'product':product,'passed':True,'groups_checked':len(rows),'idempotent':True})
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    parser.add_argument('--expect-commit')
    args = parser.parse_args()
    build_file = Path(__file__).with_name('_build_info.json')
    build = json.loads(build_file.read_text()) if build_file.exists() else None
    if args.expect_commit and (not build or build['commit_sha'] != args.expect_commit):
        raise SystemExit('installed wheel commit does not match the required commit')
    with tempfile.TemporaryDirectory(prefix='dp-offline-smoke-') as home:
        result = {'passed':True,'synthetic':True,'network_used':False,'launchd_used':False,
                  'package_version':importlib.metadata.version('data-process'),
                  'build':build,'checks':run(Path(home))}
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))


if __name__ == '__main__':
    main()
