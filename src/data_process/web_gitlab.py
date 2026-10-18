"""Project-one GET-only GitLab adapter. No configurable upstream URLs or redirects."""
import json
import re
import stat
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE = 'http://127.0.0.1:8929'
PROJECT = BASE + '/root/data-process'


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class GitLab:
    def __init__(self, token_file=None):
        self.token_file = token_file

    def get(self, path):
        p = Path(self.token_file)
        info = p.stat()
        if p.is_symlink() or not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_size > 8192:
            raise ValueError('unsafe credential file')
        config = json.loads(p.read_text())
        token = config['token']
        if not isinstance(token, str) or not token or '\n' in token or '\r' in token:
            raise ValueError('invalid credential')
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        request = urllib.request.Request(BASE + '/api/v4/projects/1/' + path, headers={'PRIVATE-TOKEN': token, 'Accept': 'application/json'})
        with opener.open(request, timeout=2) as response:
            raw = response.read(262145)
            if len(raw) > 262144:
                raise ValueError('response too large')
            return json.loads(raw)

    def summary(self, installed_sha=None):
        result = {'state': 'not_configured', 'project_url': PROJECT, 'checked_at': datetime.now(timezone.utc).isoformat(), 'main_sha': None, 'latest': None, 'installed': None}
        if not self.token_file:
            return result
        try:
            branch = self.get('repository/branches/main')
            sha = branch['commit']['id']
            if not re.fullmatch('[0-9a-f]{40}', sha):
                raise ValueError('invalid SHA')
            result['main_sha'] = sha
            pipelines = self.get('pipelines?ref=main&per_page=1')
            result['latest'] = self.pipeline(pipelines[0]) if pipelines else None
            if installed_sha and re.fullmatch('[0-9a-f]{40}', installed_sha):
                matching = self.get('pipelines?ref=main&sha=' + installed_sha + '&per_page=1')
                if matching and matching[0]['sha'] != installed_sha:
                    raise ValueError('installed SHA mismatch')
                result['installed'] = self.pipeline(matching[0]) if matching else None
            result['state'] = 'available'
        except Exception:
            result.update(state='unavailable', main_sha=None, latest=None, installed=None)
        return result

    def pipeline(self, row):
        pid = int(row['id'])
        if pid <= 0 or not re.fullmatch('[0-9a-f]{40}', row['sha']):
            raise ValueError('invalid pipeline')
        statuses = {'created', 'waiting_for_resource', 'preparing', 'pending', 'running', 'success', 'failed', 'canceled', 'skipped', 'manual', 'scheduled'}
        if row['status'] not in statuses:
            raise ValueError('unknown status')
        jobs = self.get(f'pipelines/{pid}/jobs?per_page=20')
        return {'id': pid, 'sha': row['sha'], 'status': row['status'], 'url': PROJECT + f'/-/pipelines/{pid}',
                'jobs': [{'name': j['name'], 'status': j['status']} for j in jobs if j['name'] in {'core_test', 'build_wheel', 'installed_wheel'} and j['status'] in statuses]}
