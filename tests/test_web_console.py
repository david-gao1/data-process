"""Read-only console boundary tests using disposable synthetic state."""
import hashlib
import json
from pathlib import Path

import pytest


def setup_client(tmp_path):
    from fastapi.testclient import TestClient
    from data_process.web import create_app
    from data_process.core import Platform, demo_csv, ASSET_ROOT
    home = tmp_path / 'product'
    p = Platform(home)
    p.init()
    release = p.release(ASSET_ROOT / 'definitions/daily_active.sql')
    source = tmp_path / 'source.csv'
    demo_csv(source, '2026-10-17')
    ready = p.ready('2026-10-17', source)
    run = p.submit(release, ready, '2026-10-17')
    config = {'products': {'daily_active': {'label': '三省活跃用户', 'home': str(home)}}, 'gitlab_token_file': None}
    client = TestClient(create_app(config, access_secret='test-access-secret'), base_url='http://127.0.0.1:8930')
    return client, home, run


def login(client):
    return client.post('/session', json={'secret': 'test-access-secret'}, headers={'origin': 'http://127.0.0.1:8930'})


def snapshot(home):
    return {str(p.relative_to(home)): hashlib.sha256(p.read_bytes()).hexdigest() for p in home.rglob('*') if p.is_file()}


def test_web_module_exists():
    from data_process import web
    assert callable(web.create_app)


def test_auth_and_origin_and_host(tmp_path):
    client, _, _ = setup_client(tmp_path)
    assert client.get('/api/overview').status_code == 401
    assert client.post('/session', json={'secret': 'test-access-secret'}, headers={'origin': 'https://evil.invalid'}).status_code == 403
    response = login(client)
    assert response.status_code == 200
    assert 'HttpOnly' in response.headers['set-cookie']
    assert client.get('/api/overview', headers={'host': 'evil.invalid'}).status_code == 400
    assert client.get('/api/overview', headers={'sec-fetch-site': 'cross-site'}).status_code == 403
    assert client.post('/api/overview').status_code == 405
    assert client.get('/api/overview').headers['cache-control'] == 'no-store'


def test_readonly_pagination_detail_and_unconfigured_gitlab(tmp_path):
    client, home, run = setup_client(tmp_path)
    before = snapshot(home)
    login(client)
    overview = client.get('/api/overview').json()
    assert overview['products'][0]['counts']['QUEUED'] == 1
    rows = client.get('/api/products/daily_active/runs?state=QUEUED&limit=1').json()
    assert rows['total'] == 1 and rows['items'][0]['id'] == run
    assert client.get('/api/products/daily_active/runs?state=FAILED').json()['total'] == 0
    assert client.get('/api/products/daily_active/runs?limit=51').status_code == 422
    assert client.get('/api/products/daily_active/runs?state=BOGUS').status_code == 422
    assert client.get('/api/products/daily_active/runs/' + run).json()['run']['id'] == run
    assert client.get('/api/products/nope/runs').status_code == 404
    assert client.get('/api/products/daily_active/runs/not-a-run').status_code == 404
    assert client.get('/api/gitlab').json()['state'] == 'not_configured'
    assert snapshot(home) == before


def test_missing_directory_is_not_created(tmp_path):
    from fastapi.testclient import TestClient
    from data_process.web import create_app
    home = tmp_path / 'absent'
    client = TestClient(create_app({'products': {'daily_active': {'label': '未配置', 'home': str(home)}}}, access_secret='test'), base_url='http://127.0.0.1:8930')
    client.post('/session', json={'secret': 'test'}, headers={'origin': 'http://127.0.0.1:8930'})
    assert client.get('/api/overview').json()['products'][0]['state'] == 'not_configured'
    assert not home.exists()


def test_log_and_quality_symlink_never_escape(tmp_path):
    client, home, run = setup_client(tmp_path)
    outside = tmp_path / 'private.txt'
    outside.write_text('private-secret-must-not-leak')
    candidate = home / 'candidates' / run
    candidate.mkdir(parents=True)
    (candidate / 'run.log').symlink_to(outside)
    (candidate / 'result.quality.json').symlink_to(outside)
    login(client)
    result = client.get('/api/products/daily_active/runs/' + run)
    assert result.status_code == 200
    assert 'private-secret' not in result.text
    assert result.json()['log'] == []


def test_static_assets_and_response_escape_boundary(tmp_path):
    client, _, _ = setup_client(tmp_path)
    page = client.get('/')
    assert page.status_code == 200 and '数据交付工作台' in page.text
    assert "default-src 'self'" in page.headers['content-security-policy']
    assert client.get('/assets/console.js').status_code == 200
    assert client.get('/assets/../../pyproject.toml').status_code == 404
    assert 'test-access-secret' not in page.text
    login(client)
    assert 'gitlab_token' not in client.get('/api/version').text


def test_bootstrap_is_single_use_and_bad_json_safe(tmp_path):
    client, _, _ = setup_client(tmp_path)
    origin = {'origin': 'http://127.0.0.1:8930', 'content-type': 'application/json'}
    assert client.post('/session', content='[]', headers=origin).status_code == 400
    assert client.post('/session', json={'secret': '非ASCII'}, headers=origin).status_code == 401
    assert login(client).status_code == 200
    assert login(client).status_code == 401


def test_gitlab_only_whitelisted_responses_and_exact_installed_sha(monkeypatch):
    from data_process.web_gitlab import GitLab
    gitlab = GitLab('configured')
    current, installed = 'a' * 40, 'b' * 40
    calls = []
    def get(path):
        calls.append(path)
        if path == 'repository/branches/main':
            return {'commit': {'id': current}}
        if path == 'pipelines?ref=main&per_page=1':
            return [{'id': 10, 'sha': current, 'status': 'success'}]
        if '&sha=' in path:
            return [{'id': 8, 'sha': installed, 'status': 'success'}]
        return [{'name': 'core_test', 'status': 'success', 'token': 'do-not-return'}, {'name': 'unknown', 'status': 'success'}]
    monkeypatch.setattr(gitlab, 'get', get)
    data = gitlab.summary(installed)
    assert data['state'] == 'available'
    assert data['latest']['sha'] == current and data['installed']['sha'] == installed
    assert 'do-not-return' not in json.dumps(data)
    assert data['latest']['jobs'] == [{'name': 'core_test', 'status': 'success'}]
    def fail(path):
        raise ValueError('private-token-and-internal-error')
    monkeypatch.setattr(gitlab, 'get', fail)
    data = gitlab.summary(installed)
    assert data['state'] == 'unavailable' and data['latest'] is None
    assert 'private-token' not in json.dumps(data)


def test_raw_logs_and_tampered_quality_not_exposed(tmp_path):
    client, home, run = setup_client(tmp_path)
    candidate = home / 'candidates' / run
    candidate.mkdir(parents=True)
    (candidate / 'run.log').write_text('private-source-row\ninput contract and readiness passed\n<script>alert(1)</script>\n')
    (candidate / 'result.quality.json').write_text('{"passed":true,"date":"2026-10-17"}')
    login(client)
    data = client.get('/api/products/daily_active/runs/' + run).json()
    assert data['log'] == ['input contract and readiness passed']
    assert data['quality'] is None
    assert 'private-source-row' not in json.dumps(data)


def test_gitlab_rejects_wrong_installed_commit(monkeypatch):
    from data_process.web_gitlab import GitLab
    adapter = GitLab('configured')
    def get(path):
        if path == 'repository/branches/main':
            return {'commit': {'id': 'a' * 40}}
        if path.startswith('pipelines?'):
            return [{'id': 1, 'sha': 'a' * 40, 'status': 'success'}]
        return []
    monkeypatch.setattr(adapter, 'get', get)
    assert adapter.summary('b' * 40)['state'] == 'unavailable'


def test_session_rejects_oversized_input(tmp_path):
    client, _, _ = setup_client(tmp_path)
    assert client.post('/session', json={'secret': 'x' * 1024}, headers={'origin': 'http://127.0.0.1:8930'}).status_code == 400


def test_launcher_refuses_symlink_entry_without_touching_target(tmp_path, monkeypatch):
    import sys
    import uvicorn
    from data_process.web import main
    target = tmp_path / 'keep.txt'
    target.write_text('keep existing file')
    entry = tmp_path / 'entry.html'
    entry.symlink_to(target)
    config = tmp_path / 'config.json'
    config.write_text('{"products":{}}')
    monkeypatch.setattr(sys, 'argv', ['dp-console', '--config', str(config), '--entry', str(entry)])
    monkeypatch.setattr(uvicorn, 'run', lambda *a, **kw: None)
    with pytest.raises(SystemExit, match='symlink'):
        main()
    assert target.read_text() == 'keep existing file'


@pytest.mark.parametrize('invalid', ['[]', 'null', '"bad"', '{"updated":"bad"}'])
def test_malformed_heartbeat_isolated_to_product(tmp_path, invalid):
    import sqlite3
    client, home, _ = setup_client(tmp_path)
    with sqlite3.connect(home / 'control.sqlite') as con:
        con.execute('INSERT INTO operational_status VALUES (?,?)', ('worker', invalid))
    login(client)
    result = client.get('/api/overview')
    assert result.status_code == 200
    assert result.json()['products'][0]['state'] == 'unavailable'
