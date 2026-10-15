"""Finite real-public-data acceptance, with historical replay, faults and independent raw reconciliation."""
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
import io
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
import zipfile

import openpyxl

from data_process.core import Platform, ROOT, TERMINAL
from data_process.public_retail import fetch, ingest_month, source_spec, stage_batch, verify_batch


def independent_oracle(raw, spec):
    # A separate pass over raw XLSX, never calling normalization or calculator business functions.
    with zipfile.ZipFile(raw) as archive:
        workbook = archive.read(spec['xlsx_member'])
    book = openpyxl.load_workbook(io.BytesIO(workbook), read_only=True, data_only=False)
    grouped = defaultdict(lambda: [0,0,0,0])
    profile = dict(rows=0, missing_customer=0, missing_description=0, cancellation=0,
                   negative_quantity=0, zero_price=0, negative_price=0)
    try:
        for invoice, stock, description, quantity, when, price, customer, country in book.active.iter_rows(min_row=2, values_only=True):
            profile['rows'] += 1
            profile['missing_customer'] += customer is None
            profile['missing_description'] += description is None
            cancelled = str(invoice).upper().startswith('C')
            profile['cancellation'] += cancelled
            profile['negative_quantity'] += quantity < 0
            profile['zero_price'] += price == 0
            profile['negative_price'] += price < 0
            if when.strftime('%Y-%m') not in ('2010-12','2011-01'):
                continue
            if price <= 0 or quantity == 0 or not invoice or not country or cancelled != (quantity < 0):
                continue
            amount = int(abs(Decimal(str(quantity)) * Decimal(str(price))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP) * 100)
            value = grouped[(when.date().isoformat(), country.strip())]
            if cancelled:
                value[1] += amount
                value[3] += 1
            else:
                value[0] += amount
                value[2] += 1
    finally:
        book.close()
    assert profile == {'rows':541909,'missing_customer':135080,'missing_description':1454,
                       'cancellation':9288,'negative_quantity':10624,'zero_price':2515,'negative_price':2}, profile
    return grouped, profile


def main():
    p = Platform(sys.argv[1] if len(sys.argv)>1 else ROOT/'.data-process/retail')
    p.init()
    spec = source_spec()
    raw = fetch(p)
    release = p.release(ROOT/'definitions/retail_daily.sql', 'retail_daily')
    log = (p.home/'e2e-worker.log').open('a')
    child = subprocess.Popen([sys.executable,'-m','data_process.cli','--home',str(p.home),'worker'],
                             stdout=log,stderr=subprocess.STDOUT)
    manifests = []
    all_runs = []
    def wait(run):
        deadline = time.monotonic()+180
        while p.run(run)['state'] not in TERMINAL:
            if child.poll() is not None or time.monotonic()>deadline:
                raise AssertionError('worker died or acceptance deadline exceeded')
            time.sleep(0.05)
        assert p.run(run)['state']=='SUCCEEDED',p.run(run)
    try:
        for month in ('2010-12','2011-01'):
            print(f'normalizing historical batch {month}',file=sys.stderr,flush=True)
            manifest = ingest_month(p,month)
            manifests.append(manifest)
            old_pointers = {r['date']: r['id'] for r in p.runs() if r['id'] in {a['run'] for a in p.audit()}}
            runs = stage_batch(p,manifest,release)
            for run in runs:
                wait(run)
                p.publish(run,None,'public-retail-operator','raw/source/quality reconciliation approved')
            audit_count = len(p.audit())
            assert stage_batch(p,manifest,release)==runs
            for run in runs:
                p.publish(run,None,'public-retail-operator','idempotent historical batch replay')
            assert len(p.audit())==audit_count
            if month=='2011-01':
                for date,old_run in old_pointers.items():
                    assert all(r['run_id']==old_run for r in p.trend(date,1)['rows'])
            all_runs.extend(runs)
            print(f'batch {month}: {manifest["selected_rows"]} rows, {manifest["quarantined_rows"]} quarantined, {len(runs)} dates delivered',file=sys.stderr,flush=True)
        first_run = all_runs[0]
        original = p.run(first_run)
        rerun = p.submit(release,original['source'],original['date'],key='retail-public-e2e-publication-recovery')
        wait(rerun)
        audit_count = len(p.audit())
        with p.db(True) as con:
            con.execute("CREATE TRIGGER public_e2e_publication_failure BEFORE INSERT ON audit BEGIN SELECT RAISE(ABORT,'public E2E injected failure'); END")
        try:
            try:
                p.publish(rerun,first_run,'public-retail-operator','fault injection')
            except sqlite3.IntegrityError:
                pass
            else:
                raise AssertionError('publication failure was not enforced')
            assert len(p.audit())==audit_count
            assert all(r['run_id']==first_run for r in p.trend(original['date'],1)['rows'])
        finally:
            with p.db(True) as con:
                con.execute('DROP TRIGGER public_e2e_publication_failure')
        p.publish(rerun,first_run,'public-retail-operator','explicit recovery after injected failure')
        p.publish(first_run,rerun,'public-retail-operator','historical rollback verified',rollback=True)
        print('reconciling every delivered country/day against independent raw XLSX pass',file=sys.stderr,flush=True)
        oracle,profile = independent_oracle(raw,spec)
        checked = 0
        for day in sorted({key[0] for key in oracle}):
            delivered = p.trend(day,1)['rows']
            actual = {r['country']:[r['gross_sales_pence'],r['refund_pence'],r['sale_lines'],r['refund_lines']] for r in delivered}
            expected = {country:totals for (date,country),totals in oracle.items() if date==day}
            assert actual==expected,(day,actual,expected)
            for r in delivered:
                assert r['net_sales_pence']==r['gross_sales_pence']-r['refund_pence']
                assert not {'CustomerID','InvoiceNo','Description','StockCode','source_row'} & set(r)
            checked += len(delivered)
        for manifest in manifests:
            expected = manifest['expected_totals']
            group = [v for (date,_),v in oracle.items() if date.startswith(manifest['month'])]
            assert [expected['gross_sales_pence'],expected['refund_pence'],expected['sale_lines'],expected['refund_lines']] == [sum(v[i] for v in group) for i in range(4)]
        trend = p.trend('2011-01-31')
        assert all(r['business_date']>='2011-01-02' for r in trend['rows'])
        summaries = [{k:m[k] for k in ('batch_id','month','snapshot_rows','raw_sha256','xlsx_sha256','selected_rows','quarantined_rows','quarantine_reasons','rounded_lines','expected_totals')}|{'days':len(m['sources'])} for m in manifests]
    finally:
        child.terminate()
        child.wait(timeout=10)
        log.close()
    backup = p.home.with_name(p.home.name+'-backup')
    p.backup(backup)
    restored = Platform(backup)
    assert restored.check()['integrity']=='ok'
    assert restored.trend('2011-01-31')==trend
    for manifest in manifests:
        verify_batch(restored,manifest)
    result = {'real_public_historical_data':True,'realtime_cdc':False,'home':str(p.home),
              'attribution':spec['attribution'],'license':spec['license'],'raw_bytes':raw.stat().st_size,
              'release_id':release,'batches':summaries,'raw_independent_profile':profile,
              'independently_checked_country_days':checked,'run_count':len(p.runs()),'audit_count':len(p.audit()),
              'batch_replay_idempotent':True,'publication_failure_recovery_and_rollback':True,
              'backup_restore_integrity':restored.check(),'trend_window':{'start':trend['start'],'end':trend['end'],
              'rows':len(trend['rows']),'missing_dates':trend['missing_dates']},
              'query_sample':trend['rows'][:3], 'external_uploads':0,'new_network_schedules':0}
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
