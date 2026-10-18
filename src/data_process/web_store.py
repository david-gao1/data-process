"""Bounded read-only views; no worker, initialization or business mutations."""
import json
import hashlib
import re
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

STATES = {'QUEUED', 'RUNNING', 'CANCELLING', 'SUCCEEDED', 'FAILED', 'CANCELLED', 'TIMED_OUT', 'INTERRUPTED'}
RUN_FIELDS = 'id,release,source,date,state,timeout,created,started,ended'


class Store:
    def __init__(self, products):
        self.products = products

    def product(self, product):
        if product not in self.products:
            raise KeyError('product')
        return Path(self.products[product]['home']).resolve()

    @contextmanager
    def db(self, product):
        home = self.product(product)
        path = home / 'control.sqlite'
        if path.is_symlink() or not path.is_file():
            raise FileNotFoundError('unconfigured')
        con = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=2)
        con.row_factory = sqlite3.Row
        con.execute('PRAGMA query_only=ON')
        try:
            yield con
        finally:
            con.close()

    def overview(self):
        products = []
        for key, value in self.products.items():
            entry = {'id': key, 'label': value['label'], 'state': 'available', 'counts': {}, 'latest_delivery': None, 'worker': 'unknown'}
            try:
                with self.db(key) as con:
                    entry['counts'] = {r[0]: r[1] for r in con.execute('SELECT state,COUNT(*) FROM runs GROUP BY state')}
                    entry['latest_delivery'] = con.execute('SELECT MAX(date) FROM deliveries').fetchone()[0]
                    row = con.execute("SELECT value FROM operational_status WHERE key='worker'").fetchone()
                    if row:
                        worker = json.loads(row[0])
                        if not isinstance(worker, dict):
                            raise ValueError('invalid heartbeat')
                        updated = float(worker.get('updated', 0))
                        entry['worker'] = 'active' if worker.get('status') == 'running' and 0 <= time.time() - updated <= 10 else 'inactive'
            except FileNotFoundError:
                entry['state'] = 'not_configured'
            except (sqlite3.Error, ValueError, TypeError):
                entry['state'] = 'unavailable'
                entry['counts'] = {}
            products.append(entry)
        return {'products': products}

    def runs(self, product, state=None, limit=20, offset=0):
        with self.db(product) as con:
            where = 'WHERE state=?' if state else ''
            args = [state] if state else []
            total = con.execute(f'SELECT COUNT(*) FROM runs {where}', args).fetchone()[0]
            rows = con.execute(f'SELECT {RUN_FIELDS} FROM runs {where} ORDER BY created DESC,id DESC LIMIT ? OFFSET ?', [*args, limit, offset])
            return {'items': [dict(r) for r in rows], 'total': total, 'limit': limit, 'offset': offset}

    def detail(self, product, run):
        if not re.fullmatch(r'[a-f0-9]{32}', run):
            raise KeyError('run')
        with self.db(product) as con:
            row = con.execute(f'SELECT {RUN_FIELDS},report_hash FROM runs WHERE id=?', (run,)).fetchone()
            if row is None:
                raise KeyError('run')
        home = self.product(product)
        quality = self.read_file(home, Path('candidates') / run / 'result.quality.json')
        # Logs may contain source text or credentials. Only exact worker lifecycle lines are public.
        raw_log = self.read_file(home, Path('candidates') / run / 'run.log')
        allowed = {'worker started', 'computation started', 'computation completed', 'cancel requested', 'run completed', 'input contract and readiness passed'}
        lines = [line for line in raw_log.splitlines() if line in allowed][-50:]
        report = None
        if quality and row['report_hash'] and hashlib.sha256(quality.encode()).hexdigest() == row['report_hash']:
            try:
                q = json.loads(quality)
                if type(q.get('passed')) is bool and q.get('date') == row['date']:
                    report = {'passed': q['passed'], 'date': q['date']}
            except (ValueError, TypeError):
                pass
        public_row = dict(row)
        public_row.pop('report_hash', None)
        return {'run': public_row, 'quality': report, 'log': lines, 'log_notice': '仅显示允许的状态日志；原始日志不通过门户提供。'}

    @staticmethod
    def read_file(home, relative):
        path = home / relative
        try:
            if any(part.is_symlink() for part in [path, *path.parents] if part != home.parent):
                return ''
            if not path.resolve().is_relative_to(home) or not path.is_file() or path.stat().st_size > 65536:
                return ''
            with path.open('r', encoding='utf-8', errors='replace') as stream:
                return stream.read(65536)
        except OSError:
            return ''

    def deliveries(self, product, limit=20, offset=0):
        with self.db(product) as con:
            total = con.execute('SELECT COUNT(*) FROM deliveries').fetchone()[0]
            rows = con.execute('SELECT d.date,d.run,r.release FROM deliveries d JOIN runs r ON r.id=d.run ORDER BY d.date DESC LIMIT ? OFFSET ?', (limit, offset))
            audit = con.execute('SELECT seq,date,previous_run,run,action,created FROM audit ORDER BY seq DESC LIMIT ? OFFSET ?', (limit, offset))
            return {'items': [dict(r) for r in rows], 'audit': [dict(r) for r in audit], 'total': total, 'limit': limit, 'offset': offset}
