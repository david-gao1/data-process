"""Loopback-only read-only console. Process-local access, no account or business writes."""
import argparse
import hmac
import json
import os
import secrets
import sqlite3
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse

from .web_store import Store, STATES
from .web_gitlab import GitLab

ASSETS = Path(__file__).with_name('web_assets')
CSP = "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"


def version():
    path = Path(__file__).with_name('_build_info.json')
    build = json.loads(path.read_text()) if path.is_file() else {}
    return {'commit_sha': build.get('commit_sha'), 'version': build.get('version', '开发版本'), 'mode': 'installed' if build else 'development'}


def create_app(config, access_secret):
    if not access_secret:
        raise ValueError('access secret required')
    port = int(config.get('port', 8930))
    host = f'127.0.0.1:{port}'
    origin = 'http://' + host
    store = Store(config.get('products', {}))
    gitlab = GitLab(config.get('gitlab_token_file'))
    cookie = secrets.token_urlsafe(32)
    bootstrap_used = False
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware('http')
    async def boundary(request, call_next):
        if request.headers.get('host') != host:
            response = JSONResponse({'error': 'invalid host'}, status_code=400)
        elif ((request.url.path.startswith('/api/') or request.url.path == '/session')
              and (request.headers.get('origin') not in (None, origin)
                   or request.headers.get('sec-fetch-site') not in (None, 'none', 'same-origin'))):
            response = JSONResponse({'error': 'cross-site request denied'}, status_code=403)
        elif request.url.path.startswith('/api/') and not hmac.compare_digest(request.cookies.get('dp_session', '').encode(), cookie.encode()):
            response = JSONResponse({'error': '请使用本机安全入口打开门户'}, status_code=401)
        else:
            response = await call_next(request)
        response.headers.update({'Cache-Control': 'no-store', 'Content-Security-Policy': CSP,
                                 'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer',
                                 'X-Frame-Options': 'DENY'})
        return response

    @app.post('/session')
    async def session(request: Request):
        nonlocal bootstrap_used
        if request.headers.get('origin') != origin or request.headers.get('content-type', '').split(';')[0] != 'application/json':
            raise HTTPException(403, 'same origin JSON required')
        body = b''
        async for chunk in request.stream():
            body += chunk
            if len(body) > 512:
                raise HTTPException(400, 'invalid request')
        try:
            submitted = json.loads(body).get('secret', '')
        except (ValueError, AttributeError):
            raise HTTPException(400, 'invalid request') from None
        if not isinstance(submitted, str) or not hmac.compare_digest(submitted.encode(), access_secret.encode()) or bootstrap_used:
            raise HTTPException(401, 'invalid or used entry')
        bootstrap_used = True
        response = JSONResponse({'authenticated': True})
        response.set_cookie('dp_session', cookie, httponly=True, samesite='strict', path='/')
        return response

    @app.get('/')
    def index():
        return FileResponse(ASSETS / 'index.html', media_type='text/html')

    @app.get('/assets/{name}')
    def asset(name: str):
        if name not in {'console.css', 'console.js'}:
            raise HTTPException(404)
        return FileResponse(ASSETS / name)

    @app.get('/api/overview')
    def overview():
        return store.overview()

    def read(function, *args, **kwargs):
        try:
            return function(*args, **kwargs)
        except KeyError:
            raise HTTPException(404, '未找到产品或运行') from None
        except FileNotFoundError:
            raise HTTPException(404, '产品未配置') from None
        except (sqlite3.Error, ValueError, OSError):
            raise HTTPException(503, '数据暂不可用') from None

    @app.get('/api/products/{product}/runs')
    def runs(product: str, state: str | None = None, limit: int = Query(20, ge=1, le=50), offset: int = Query(0, ge=0, le=100000)):
        if state and state not in STATES:
            raise HTTPException(422, 'invalid state')
        return read(store.runs, product, state, limit, offset)

    @app.get('/api/products/{product}/runs/{run}')
    def detail(product: str, run: str):
        return read(store.detail, product, run)

    @app.get('/api/products/{product}/deliveries')
    def deliveries(product: str, limit: int = Query(20, ge=1, le=50), offset: int = Query(0, ge=0, le=100000)):
        return read(store.deliveries, product, limit, offset)

    @app.get('/api/version')
    def build():
        return version()

    @app.get('/api/gitlab')
    def engineering():
        return gitlab.summary(version()['commit_sha'])

    return app


def main():
    parser = argparse.ArgumentParser(description='本机只读数据交付工作台')
    parser.add_argument('--config', required=True, help='服务端产品目录配置JSON；不接受浏览器传入路径')
    parser.add_argument('--entry', required=True, help='本地0600安全入口HTML输出文件')
    parser.add_argument('--port', type=int, default=8930, choices=range(8930, 9000))
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text())
    config['port'] = args.port
    secret = secrets.token_urlsafe(32)
    raw_entry = Path(args.entry).expanduser()
    entry = raw_entry.parent.resolve() / raw_entry.name
    entry.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if entry.is_symlink():
        raise SystemExit('entry must not be a symlink')
    content = '<!doctype html><meta charset="utf-8"><title>打开工作台</title><script>location.replace(' + json.dumps(f'http://127.0.0.1:{args.port}/#' + secret) + ')</script>'
    fd = os.open(entry, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    with os.fdopen(fd, 'w') as stream:
        os.fchmod(stream.fileno(), 0o600)
        stream.write(content)
    print('本机入口已写入指定文件（0600）；请在浏览器打开。关闭浏览器后需重新打开入口时，重启此进程。', flush=True)
    import uvicorn
    uvicorn.run(create_app(config, secret), host='127.0.0.1', port=args.port, access_log=False, log_level='warning')


if __name__ == '__main__':
    main()
