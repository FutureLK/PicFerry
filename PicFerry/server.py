import http.server
import socketserver
import webbrowser
import sys
import signal
import threading
import time
# 一方模块导入期逐模块计时(debug 诊断): 数据常驻 logging_util.IMPORT_TIMING,
# debugMode 由关转开时由 handler 补发, 无需重启
_t_imp = time.perf_counter()
import logging_util
from logging_util import console_log
logging_util.IMPORT_TIMING['logging_util'] = round((time.perf_counter() - _t_imp) * 1000)

_t_imp = time.perf_counter()
from config_store import load_config
logging_util.IMPORT_TIMING['config_store'] = round((time.perf_counter() - _t_imp) * 1000)

_t_imp = time.perf_counter()
from handler import SyncHandler
logging_util.IMPORT_TIMING['handler'] = round((time.perf_counter() - _t_imp) * 1000)

PORT = 13826


# ─── Server ──────────────────────────────────────────────────────────────────

class ThreadedServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    allow_reuse_address = True
    daemon_threads = True

def main():
    bind_host = '0.0.0.0' if load_config().get('allowLan') else '127.0.0.1'
    server = ThreadedServer((bind_host, PORT), SyncHandler)

    sys.stderr.write(f'PicFerry - LAN File Sync: http://127.0.0.1:{PORT}\n')
    sys.stderr.flush()
    console_log('DONE', '服务器就绪')
    console_log('DONE', '仅本机访问 127.0.0.1' if bind_host == '127.0.0.1' else '局域网访问已开启 0.0.0.0')

    webbrowser.open(f'http://127.0.0.1:{PORT}')

    def shutdown(sig, frame):
        print('\n  关闭中...')
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\n  关闭中...')
        server.shutdown()

if __name__ == '__main__':
    main()
