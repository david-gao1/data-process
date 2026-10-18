"""Verify the installed console over loopback; no business state or external requests."""
import argparse
import http.cookiejar
import json
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--expect-commit', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='dp-console-smoke-') as temp:
        root = Path(temp)
        config, entry = root / 'config.json', root / 'entry.html'
        config.write_text('{"products":{}}')
        # Select an unused loopback port in the console's deliberately narrow range.
        for port in range(8940, 9000):
            with socket.socket() as sock:
                try:
                    sock.bind(('127.0.0.1', port))
                    break
                except OSError:
                    continue
        else:
            raise SystemExit('no console smoke port available')
        process = subprocess.Popen([sys.executable, '-I', '-m', 'data_process.web', '--config', str(config), '--entry', str(entry), '--port', str(port)], cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        base = f'http://127.0.0.1:{port}'
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        try:
            for _ in range(100):
                try:
                    with opener.open(base, timeout=1) as response:
                        assert '数据交付工作台' in response.read().decode()
                    break
                except (urllib.error.URLError, ConnectionError):
                    if process.poll() is not None:
                        raise RuntimeError('console process exited') from None
                    time.sleep(0.1)
            else:
                raise RuntimeError('console startup timeout')
            redirect = json.loads(re.search(r'location.replace\(("[^"]+")\)', entry.read_text()).group(1))
            secret = urllib.parse.urlsplit(redirect).fragment
            request = urllib.request.Request(base + '/session', data=json.dumps({'secret': secret}).encode(), headers={'Origin': base, 'Content-Type': 'application/json'})
            with opener.open(request, timeout=2) as response:
                assert json.load(response)['authenticated']
            with opener.open(base + '/api/version', timeout=2) as response:
                assert json.load(response)['commit_sha'] == args.expect_commit
            with opener.open(base + '/api/overview', timeout=2) as response:
                assert json.load(response)['products'] == []
            with opener.open(base + '/api/gitlab', timeout=2) as response:
                assert json.load(response)['state'] == 'not_configured'
            for asset in ('console.js', 'console.css'):
                with opener.open(base + '/assets/' + asset, timeout=2) as response:
                    assert len(response.read()) > 100
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
    report = {'passed': True, 'commit_sha': args.expect_commit, 'installed_http_console': True, 'only_loopback_network': True, 'business_state_used': False, 'gitlab_credentials_used': False}
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
