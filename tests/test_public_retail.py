"""Public ingestion faults and retail business rules with tiny synthetic XLSX fixtures."""
from datetime import datetime
from decimal import Decimal
import io
import json
from pathlib import Path
import shutil
import sqlite3
import zipfile

import openpyxl
import pytest

from data_process.core import Platform, ROOT, digest
from data_process.public_retail import (HEADERS, OFFICIAL_URL, fetch, ingest_month, normalized_row,
                                        stage_batch, verify_batch, transfer_https)
from data_process.worker import worker


def archive_fixture(tmp_path, rows, headers=HEADERS):
    # Disposable parser fixture, never a user-facing spreadsheet or real source modification.
    book = openpyxl.Workbook()
    book.active.append(headers)
    for row in rows:
        book.active.append(row)
    buf = io.BytesIO()
    book.save(buf)
    workbook = buf.getvalue()
    path = tmp_path / 'fixture.zip'
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('Online Retail.xlsx', workbook)
    spec = {'dataset':'uci-online-retail-352','url':OFFICIAL_URL,'page':'https://archive.ics.uci.edu/dataset/352/online%2Bretail',
            'license':'CC-BY-4.0','attribution':'synthetic test fixture, not public source evidence',
            'max_bytes':33554432,'expected_sha256':digest(path.read_bytes()),
            'expected_xlsx_sha256':digest(workbook),'xlsx_member':'Online Retail.xlsx'}
    return path, spec


def row(invoice='10001', quantity=2, price=1.25, day='2010-12-01', country='United Kingdom'):
    return [invoice, 'SKU', None, quantity, datetime.fromisoformat(day), price, None, country]


@pytest.fixture
def product(tmp_path):
    p = Platform(tmp_path / 'retail')
    p.init()
    return p


def copied(raw):
    return lambda _url, destination, _limit: shutil.copyfile(raw, destination)


def test_bounded_fetch_hash_cache_and_no_retry(product, tmp_path):
    raw, spec = archive_fixture(tmp_path, [row()])
    calls = []
    def transfer(url, destination, limit):
        calls.append(url)
        shutil.copyfile(raw, destination)
    cached = fetch(product, spec, transfer)
    assert cached.read_bytes() == raw.read_bytes() and len(calls) == 1
    fetch(product, spec, lambda *_: pytest.fail('cache unexpectedly used network'))
    assert json.loads(cached.with_suffix('.json').read_text())['license'] == 'CC-BY-4.0'
    cached.with_suffix('.json').unlink()
    fetch(product, spec, lambda *_: pytest.fail('validated cache recovery unexpectedly downloaded'))
    assert 'recovered' in cached.with_suffix('.json').read_text()
    cached.write_bytes(b'corrupt')
    with pytest.raises(ValueError, match='checksum'):
        fetch(product, spec, transfer)


def test_network_bad_hash_size_source_and_archive_fail_closed(product, tmp_path):
    raw, spec = archive_fixture(tmp_path, [row()])
    def failed(*_):
        raise OSError('simulated network failure')
    with pytest.raises(OSError):
        fetch(product, spec, failed)
    assert not list((product.home / 'raw').glob('*.zip'))
    with pytest.raises(ValueError, match='checksum'):
        fetch(product, spec, lambda _, target, __: Path(target).write_bytes(b'partial'))
    small = dict(spec, max_bytes=1)
    with pytest.raises(ValueError, match='size'):
        fetch(product, small, copied(raw))
    with pytest.raises(ValueError, match='registered'):
        fetch(product, dict(spec, url='https://example.com/private'), copied(raw))
    invalid = tmp_path / 'invalid.zip'
    invalid.write_bytes(b'not an archive')
    with pytest.raises(ValueError, match='ZIP'):
        fetch(product, dict(spec, expected_sha256=digest(invalid.read_bytes())), copied(invalid))
    assert not product.runs() and not product.audit()


def test_transfer_enforces_actual_stream_limit_and_terminates_child(tmp_path, monkeypatch):
    class FakeCurl:
        def __init__(self):
            self.stdout = io.BytesIO(b'x' * 131072)
            self.done = False
        def poll(self): return 0 if self.done else None
        def terminate(self): self.done = True
        def wait(self, timeout=None): self.done = True; return 0
    fake = FakeCurl()
    monkeypatch.setattr('data_process.public_retail.subprocess.Popen', lambda *_args, **_kwargs: fake)
    with pytest.raises(ValueError, match='byte limit'):
        transfer_https(OFFICIAL_URL, tmp_path / 'partial.zip', 65536)
    assert fake.done and (tmp_path / 'partial.zip').stat().st_size <= 65536


def test_missing_columns_and_excessive_anomalies_do_not_mark_ready(product, tmp_path):
    raw, spec = archive_fixture(tmp_path, [], ['wrong'])
    raw = fetch(product, spec, copied(raw))
    with pytest.raises(ValueError, match='schema'):
        ingest_month(product, '2010-12', spec, raw)
    # Different fixture file, every row has invalid price.
    input_file, other = archive_fixture(tmp_path, [row(price=0)])
    other_raw = fetch(product, other, copied(input_file))
    with pytest.raises(ValueError, match='5%'):
        ingest_month(product, '2010-12', other, other_raw)
    with product.db() as con:
        assert con.execute('SELECT COUNT(*) FROM sources').fetchone()[0] == 0
    assert not product.runs()


def test_exact_money_cancellation_and_missing_optional_fields():
    clean, reason, rounded = normalized_row(row(quantity=1, price=1.005), 2)
    assert clean == ['2010-12-01','United Kingdom','sale',101,2] and rounded and reason is None
    clean, reason, _ = normalized_row(row(invoice='C100', quantity=-2, price=1.25), 3)
    assert clean[2:4] == ['refund', 250] and reason is None
    assert normalized_row(row(quantity=-2), 4)[1] == 'cancellation_sign_mismatch'
    assert normalized_row(row(invoice='C100', quantity=2), 5)[1] == 'cancellation_sign_mismatch'
    assert normalized_row(row(price=-1), 6)[1] == 'nonpositive_price'
    assert normalized_row(row(country=None), 7)[1] == 'missing_dimension'
    assert normalized_row(row(price=float('nan')), 8)[1] == 'nonpositive_price'


def test_two_batches_idempotence_publish_failure_restore_and_private_schema(product, tmp_path):
    p = product
    records = [row() for _ in range(25)] + [row(invoice='C100',quantity=-1,price=1.005)] + [row(price=0)]
    records += [row(day='2011-01-04',country='Germany',quantity=3,price=2.5)]
    raw, spec = archive_fixture(tmp_path, records)
    raw = fetch(p, spec, copied(raw))
    first = ingest_month(p, '2010-12', spec, raw)
    assert first['quarantined_rows'] == 1 and first['expected_totals']['net_sales_pence'] == 6149
    assert first['snapshot_missing_customer'] == len(records)
    assert ingest_month(p, '2010-12', spec, raw)['batch_id'] == first['batch_id']
    release = p.release(ROOT / 'definitions/retail_daily.sql', 'retail_daily')
    with pytest.raises(ValueError, match='one product'):
        p.release(ROOT / 'definitions/daily_active.sql')
    runs = stage_batch(p, first, release)
    worker(p, once=True)
    assert p.run(runs[0])['state'] == 'SUCCEEDED'
    assert p.trend('2010-12-01')['rows'] == []
    with p.db(True) as con:
        con.execute("CREATE TRIGGER public_publish_failure BEFORE INSERT ON audit BEGIN SELECT RAISE(ABORT,'injected publication failure'); END")
    with pytest.raises(sqlite3.IntegrityError):
        p.publish(runs[0], None, 'review', 'must remain unpublished')
    assert not p.audit() and not p.trend('2010-12-01')['rows']
    with p.db(True) as con:
        con.execute('DROP TRIGGER public_publish_failure')
    p.publish(runs[0], None, 'review', 'explicit recovery')
    assert stage_batch(p, first, release) == runs
    p.publish(runs[0], None, 'review', 'repeat must be idempotent')
    second = ingest_month(p, '2011-01', spec, raw)
    next_run = stage_batch(p, second, release)[0]
    worker(p, once=True)
    p.publish(next_run, None, 'review', 'second historical month')
    assert len(p.runs()) == 2 and len(p.audit()) == 2
    assert p.trend('2010-12-01')['rows'][0]['run_id'] == runs[0]
    output = p.trend('2011-01-04')['rows']
    assert output[-1]['net_sales_pence'] == 750
    assert not {'CustomerID','InvoiceNo','Description','StockCode','source_row'} & set(output[-1])
    assert verify_batch(p, first)['integrity'] == 'ok'
    backup = tmp_path / 'backup'
    p.backup(backup)
    restored = Platform(backup)
    assert restored.check()['integrity'] == 'ok'
    assert restored.trend('2011-01-04') == p.trend('2011-01-04')
    damaged = dict(first, month='2011-02')
    with pytest.raises(ValueError, match='manifest'):
        verify_batch(p, damaged)


def test_broken_workbook_and_unexpected_members_are_rejected(product, tmp_path):
    bad_workbook = b'not an xlsx zip'
    path = tmp_path / 'broken.zip'
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('Online Retail.xlsx', bad_workbook)
    spec = {'dataset':'uci-online-retail-352','url':OFFICIAL_URL,'page':'official test source',
            'license':'CC-BY-4.0','attribution':'synthetic fixture','max_bytes':33554432,
            'expected_sha256':digest(path.read_bytes()),'expected_xlsx_sha256':digest(bad_workbook),
            'xlsx_member':'Online Retail.xlsx'}
    with pytest.raises(zipfile.BadZipFile):
        fetch(product, spec, copied(path))
    good, other = archive_fixture(tmp_path, [row()])
    with zipfile.ZipFile(good, 'a') as archive:
        archive.writestr('../escape.csv', 'unexpected')
    other['expected_sha256'] = digest(good.read_bytes())
    with pytest.raises(ValueError, match='unexpected archive'):
        fetch(product, other, copied(good))
    assert not list((product.home/'raw').glob('*.zip'))
    assert not (product.home.parent/'escape.csv').exists()
    with product.db() as con:
        assert con.execute('SELECT COUNT(*) FROM sources').fetchone()[0] == 0
