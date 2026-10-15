"""Standalone release calculator for normalized public retail invoice aggregates."""
from collections import defaultdict
import csv
import hashlib
import json
import os
from pathlib import Path
import sys
import threading
import time

import duckdb

COLUMNS = ['business_date', 'country', 'gross_sales_pence', 'refund_pence', 'net_sales_pence', 'sale_lines', 'refund_lines']


def checksum(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def calculate(spec):
    source, output = Path(spec['source']), Path(spec['output'])
    if checksum(source) != spec['source_hash']:
        raise ValueError('retail source checksum mismatch')
    totals = defaultdict(lambda: [0, 0, 0, 0])
    identities = set()
    with source.open(newline='', encoding='utf-8') as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != ['business_date', 'country', 'line_type', 'amount_pence', 'source_row']:
            raise ValueError('retail source schema mismatch')
        for row in reader:
            amount, ordinal = int(row['amount_pence']), int(row['source_row'])
            if (row['business_date'] != spec['date'] or not row['country'].strip()
                    or row['line_type'] not in {'sale', 'refund'} or amount < 0 or amount > 10**14
                    or ordinal < 2 or ordinal in identities or None in row):
                raise ValueError('retail source row invalid')
            identities.add(ordinal)
            values = totals[row['country']]
            offset = 0 if row['line_type'] == 'sale' else 1
            values[offset] += amount
            values[2 + offset] += 1
    if not totals:
        raise ValueError('retail input not ready: empty date partition')
    oracle = sorted((spec['date'], country, gross, refund, gross - refund, sales, refunds)
                    for country, (gross, refund, sales, refunds) in totals.items())
    print('input contract and readiness passed', flush=True)
    time.sleep(spec['delay'])
    with duckdb.connect(config={'threads': 1, 'memory_limit': '256MB'}) as con:
        con.execute('CREATE TABLE invoice_lines AS SELECT * FROM read_csv(?, all_varchar=true)', [str(source)])
        con.execute('SET enable_external_access=false')
        result = con.execute(Path(spec['sql']).read_text(), {'business_date': spec['date']})
        if [c[0] for c in result.description] != COLUMNS or sorted(result.fetchall()) != oracle:
            raise ValueError('retail quality failed: independent integer oracle mismatch')
    with duckdb.connect(config={'threads': 1, 'memory_limit': '256MB'}) as con:
        con.execute('CREATE TABLE result(business_date VARCHAR,country VARCHAR,gross_sales_pence BIGINT,refund_pence BIGINT,net_sales_pence BIGINT,sale_lines BIGINT,refund_lines BIGINT)')
        con.executemany('INSERT INTO result VALUES (?,?,?,?,?,?,?)', oracle)
        con.execute('COPY result TO ? (FORMAT PARQUET)', [str(output)])
    report = {'passed': True, 'date': spec['date'], 'rows': len(oracle), 'source_hash': spec['source_hash'],
              'output_hash': checksum(output), 'product': 'retail_daily', 'line_count': len(identities)}
    report_path = output.with_suffix('.quality.json')
    report_path.write_text(json.dumps(report, sort_keys=True))
    for path in (output, report_path):
        with path.open('rb') as stream:
            os.fsync(stream.fileno())
    fd = os.open(output.parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    print(json.dumps(report), flush=True)


if __name__ == '__main__':
    spec = json.loads(Path(sys.argv[1]).read_text())
    def guard():
        while True:
            if os.getppid() != spec['parent_pid']:
                os._exit(73)
            time.sleep(0.1)
    threading.Thread(target=guard, daemon=True).start()
    calculate(spec)
