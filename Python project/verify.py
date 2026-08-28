"""PicFerry 冒烟验证脚本（纯标准库, 零依赖）。

对 server.py 执行 py_compile, 然后把 server.py 复制到系统临时目录隔离启动
（config/ 也建在临时目录, 不触碰仓库内真实配置）, 服务就绪后依次断言:
  a. GET / 返回 200 且含 "PicFerry"
  b. GET /api/config 返回 200 且为 JSON
  c. 带伪造 Origin: http://evil.com 的 GET /api/list 必须返回 403
  d. GET /api/list?url=<含 2 张图片的临时目录> 返回 files 数量为 2
  e. GET /api/logs?since=0 返回 next_id > 0
  f. GET /api/log 写入探针日志后, since=<next_id> 增量轮询只返回该条且 next_id 前进
  g. since 超前于 next_id 时 truncated 为 True 且 logs 为空

用法: python verify.py
全部通过打印 ALL CHECKS PASSED 并以 0 退出; 任一失败打印失败项并以非零码退出。
运行会弹出一次浏览器窗口（服务副本的 webbrowser.open）, 属正常, 忽略即可。
"""

import base64
import json
import py_compile
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# 与 server.py 的 PORT 保持一致
HOST = '127.0.0.1'
PORT = 13826
READY_TIMEOUT = 30.0          # 等服务就绪的总时长（秒）
BASE = Path(__file__).resolve().parent
SERVER_SRC = BASE / 'server.py'

# 1×1 合法 PNG 字节（base64 内嵌）, 不依赖"空文件也会被列出"的实现细节
PNG_1PX = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ'
    'AAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=='
)

FAILURES = []   # 收集断言失败项, 结束时统一报告


def fail_env(msg):
    """环境性失败（端口占用/编译失败/服务起不来）: 无法继续, 打印后立即退出。
    SystemExit 会穿透 finally/with → 子进程仍被 stop() 终止, 临时目录仍被清理。"""
    print(f'FAIL: {msg}')
    sys.exit(1)


def check(name, ok, detail=''):
    if ok:
        print(f'PASS: {name}')
    else:
        FAILURES.append(f'{name}（{detail}）' if detail else name)
        print(f'FAIL: {name} — {detail}')


def port_free():
    try:
        with socket.create_connection((HOST, PORT), timeout=0.5):
            return False   # 连得上 = 已有实例在监听
    except OSError:
        return True


def http_get(path, headers=None, timeout=10):
    """GET 并统一返回 (status, body); 4xx/5xx 不抛异常, 同样返回 (code, body)"""
    req = urllib.request.Request(f'http://{HOST}:{PORT}{path}', headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def seed_config(tmp, imgs):
    """预置服务副本的 config.ini: 把 dev1ceA 声明基座指向测试图片目录。
    必须 UTF-8 无 BOM（server.py 按 BOM 视作坏文件）"""
    config_dir = tmp / 'config'
    config_dir.mkdir()
    (config_dir / 'config.ini').write_text(
        '[Settings]\n'
        f'dev1ceA = {imgs}\n',
        encoding='utf-8')


def print_server_log(log_path, tail=40):
    """打印服务进程输出尾部（剥 ANSI 色码）, 用于失败定位"""
    try:
        text = Path(log_path).read_text(encoding='utf-8', errors='replace')
    except OSError:
        return
    lines = text.splitlines()[-tail:]
    print(f'--- 服务进程输出（末 {len(lines)} 行）---')
    for line in lines:
        print('    ' + re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', line))
    print('---')


def wait_ready(proc, log_path):
    """轮询直到 HTTP 服务可响应; 进程提前退出立即报错"""
    url = f'http://{HOST}:{PORT}/'
    deadline = time.time() + READY_TIMEOUT
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f'服务进程提前退出（exit={proc.returncode}）')
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                resp.read()
                return
        except urllib.error.HTTPError:
            return   # 有 HTTP 响应（含 4xx/5xx）即视为就绪
        except (urllib.error.URLError, OSError):
            time.sleep(0.25)
    raise RuntimeError(f'等待 {HOST}:{PORT} 就绪超时（{READY_TIMEOUT:.0f}s）')


def stop(proc):
    """终止服务子进程: 先 terminate, 10s 不退再 kill"""
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass


def run_assertions(imgs):
    """七条断言: a 首页 / b 配置 JSON / c 同源闸门 403 / d 本地基座列目录 /
    e 日志 next_id>0 / f 日志增量轮询 / g 日志 truncated 语义"""
    status, body = http_get('/')
    check('a. GET / 返回 200 且含 "PicFerry"',
          status == 200 and 'PicFerry' in body.decode('utf-8', 'replace'),
          f'status={status}')

    status, body = http_get('/api/config')
    ok, detail = False, f'status={status}'
    if status == 200:
        try:
            json.loads(body.decode('utf-8'))
            ok = True
        except (UnicodeDecodeError, ValueError) as e:
            detail = f'响应不是合法 JSON — {e}'
    check('b. GET /api/config 返回 200 且为 JSON', ok, detail)

    status, _ = http_get('/api/list', headers={'Origin': 'http://evil.com'})
    check('c. 伪造 Origin 的 GET /api/list 必须返回 403', status == 403,
          f'status={status}')

    status, body = http_get('/api/list?' + urllib.parse.urlencode({'url': str(imgs)}))
    ok, detail = False, f'status={status}'
    if status == 200:
        try:
            data = json.loads(body.decode('utf-8'))
        except (UnicodeDecodeError, ValueError) as e:
            detail = f'响应不是合法 JSON — {e}'
        else:
            if 'error' in data:
                detail = f'服务端报错 — {data["error"]}'
            else:
                n = len(data.get('files', []))
                ok, detail = (n == 2), f'files 数量={n}（期望 2）'
    check('d. GET /api/list?url=<临时图片目录> 返回 files 数量为 2', ok, detail)

    # e/f/g: 日志增量轮询协议（回归防线: LOG_LAST_ID 的 from-import 快照曾使 next_id 恒为 0;
    # 各断言之间服务端无其他日志写入源, 探针是两轮轮询间唯一新增, 断言确定性成立）
    status, body = http_get('/api/logs?since=0')
    ok, detail, next_id = False, f'status={status}', 0
    if status == 200:
        try:
            data = json.loads(body.decode('utf-8'))
        except (UnicodeDecodeError, ValueError) as e:
            detail = f'响应不是合法 JSON — {e}'
        else:
            next_id = data.get('next_id', 0)
            ok = isinstance(next_id, int) and next_id > 0
            detail = f'next_id={next_id!r}'
    check('e. GET /api/logs?since=0 返回 next_id > 0', ok, detail)

    status, body = http_get('/api/log?' + urllib.parse.urlencode(
        {'msg': 'verify-log-probe', 'cat': 'INFO'}))
    probe_ok = status == 200
    detail = f'status={status}'
    status, body = http_get('/api/logs?since=' + str(next_id))
    ok = False
    if probe_ok and status == 200:
        try:
            data = json.loads(body.decode('utf-8'))
        except (UnicodeDecodeError, ValueError) as e:
            detail = f'响应不是合法 JSON — {e}'
        else:
            logs = data.get('logs', [])
            ok = (len(logs) == 1 and logs[0].get('msg') == 'verify-log-probe'
                  and logs[0].get('id', 0) > next_id and data.get('next_id', 0) > next_id)
            detail = f'logs={logs!r} next_id={data.get("next_id")!r}'
    elif not probe_ok:
        detail = f'探针写入失败, status={detail}'
        ok = False
    check('f. 写入探针日志后, since=<next_id> 只返回该条且 next_id 前进', ok, detail)

    status, body = http_get('/api/logs?since=' + str(next_id + 1000))
    ok, detail = False, f'status={status}'
    if status == 200:
        try:
            data = json.loads(body.decode('utf-8'))
        except (UnicodeDecodeError, ValueError) as e:
            detail = f'响应不是合法 JSON — {e}'
        else:
            ok = data.get('truncated') is True and data.get('logs') == []
            detail = f'truncated={data.get("truncated")!r} logs={data.get("logs")!r}'
    check('g. since 超前于 next_id 时 truncated 为 True 且 logs 为空', ok, detail)


def main():
    if not SERVER_SRC.is_file():
        fail_env(f'未找到 {SERVER_SRC}')
    if not port_free():
        fail_env(f'{HOST}:{PORT} 已被占用 — 请先关闭正在运行的 PicFerry 再执行本脚本')

    try:
        py_compile.compile(str(SERVER_SRC), doraise=True)
    except py_compile.PyCompileError as e:
        fail_env(f'py_compile server.py 失败 — {e}')
    print('PASS: py_compile server.py')

    with tempfile.TemporaryDirectory(prefix='picferry_verify_') as tmp_name:
        tmp = Path(tmp_name)
        imgs = tmp / 'imgs'
        imgs.mkdir()
        (imgs / 'a.png').write_bytes(PNG_1PX)
        (imgs / 'b.png').write_bytes(PNG_1PX)
        seed_config(tmp, imgs)
        shutil.copy2(SERVER_SRC, tmp / 'server.py')
        shutil.copy2(BASE / 'logging_util.py', tmp / 'logging_util.py')
        shutil.copy2(BASE / 'config_store.py', tmp / 'config_store.py')
        shutil.copy2(BASE / 'pathsafety.py', tmp / 'pathsafety.py')
        shutil.copy2(BASE / 'datasources.py', tmp / 'datasources.py')

        log_path = tmp / 'server_output.log'
        with open(log_path, 'wb') as log_file:
            proc = subprocess.Popen(
                [sys.executable, str(tmp / 'server.py')],
                cwd=str(tmp), stdout=log_file, stderr=subprocess.STDOUT)
            try:
                try:
                    wait_ready(proc, log_path)
                except RuntimeError as e:
                    print_server_log(log_path)
                    fail_env(f'服务启动失败 — {e}')
                run_assertions(imgs)
            finally:
                stop(proc)

    if FAILURES:
        print()
        print(f'{len(FAILURES)} 项检查失败:')
        for item in FAILURES:
            print(f'  - {item}')
        sys.exit(1)
    print()
    print('ALL CHECKS PASSED')


if __name__ == '__main__':
    main()
