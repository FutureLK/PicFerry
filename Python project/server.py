import http.server
import json
import urllib.request
import urllib.error
import urllib.parse
import ftplib
import hashlib
import socketserver
import webbrowser
import re
import io
import os
import sys
import signal
import datetime
import threading
import time
import mimetypes
import configparser
import logging_util
from logging_util import LOG_COLORS, RESET, _USE_COLOR, LOG_BUFFER, LOG_SEQ, LOG_LOCK, console_log
from config_store import CONFIG_DIR, load_config, save_config
from pathsafety import is_local_path, strip_file_prefix, _safe_error_text, _sanitize_rel_path, _declared_local_bases, _check_local_base, _check_realpath_within, _assert_declared_scan_base
from datasources import IMAGE_EXTS, is_ftp, resolve_url, parse_ftp_info, http_fetch, http_download, http_put, ftp_list, ftp_download, ftp_upload, parse_html_listing, local_list, _read_remote_file
from webassets import HTML

PORT = 13826


# ─── Frontend HTML（webassets.py 从 static/ 装配） ───────────────────────────────────────────────────────────


# ─── Pixiv API ────────────────────────────────────────────────────────────
#
# 接口文档（供后期维护参考）
#
# [POST] /api/pixiv/bookmarks
#   描述: 启动 Pixiv 收藏扫描（后台 Job, 立即返回; 进度经 /api/pixiv/job 轮询）
#   请求头: Content-Type: application/json
#   请求体: {
#     "uid":       string  — Pixiv 用户 ID（必填）
#     "phpsessid": string  — 浏览器 Cookie 中的 PHPSESSID（必填）
#     "path":      string  — 本地文件夹路径或 FTP/HTTP 链接（必填）
#     "limit":     int     — 扫描数量上限, 0=全部（可选, 默认取 config pixivLimit）
#   }
#   成功响应: { "ok": true, "status": "fetching" }   （单槽: 已有任务运行时返回 {"error":"已有任务在运行"}）
#   错误响应: { "error": string }
#
# [POST] /api/pixiv/bookmarks/stop
#   描述: 请求终止当前扫描（网络请求阶段最长等当前请求超时 30s; 本地扫描阶段等扫描完成后生效）
#   成功响应: { "ok": true }
#
# [GET] /api/pixiv/job
#   描述: 轮询 Job 状态（不含 result 数组, 轻量）
#   成功响应: { "status": "idle|fetching|scanning|matching|done|stopped|error",
#               "progress": {"phase","fetched","total"}, "error": string|null,
#               "summary": {"total_bookmarks","local_count","missing_works","missing_pages"}|null }
#
# [GET] /api/pixiv/job/result
#   描述: 取终态结果（仅 done 时有数据）
#   成功响应: { "matched": [{illust_id, pageCount, saved_pages, missing_pages, range}, ...] }
#
# 查重语义: 本地文件名 ^(\d+)_p(\d+) 提取 (illust_id, page);
#   page < 书签 pageCount 判定该分p已收藏（0-indexed）; 无 _pN 后缀按 page 0。
# 黑名单: 拉取循环内剔除 blacklist.csv 中的作品 ID, 不计入 limit 预算。
# 请求间隔: config pixivInterval (秒, 默认 0.8) 防限流。
#
# 如需新增 Pixiv 功能（如拉取指定画师作品、关键词搜索），
# 可在此文件新增函数并在 SyncHandler 中注册新路由:
#   def _handle_pixiv_xxx(self):    # handler
#   elif parsed.path == '/api/pixiv/xxx': self._handle_pixiv_xxx()   # do_POST / do_GET
#
# 【扩展新功能三步】1) 后端: 新增 handler 方法 + 在 do_GET/do_POST 注册路由
#   2) 前端: 在 static/index.html 加控件/面板（或按 TABS 注册表新增标签页）
#   3) 验证: 参考 .omo/evidence/pixiv-web-upgrade/ 各 task 的 QA 模式写 curl/Playwright 验收

from pixiv import pixiv_job, _start_pixiv_job, load_blacklist, save_blacklist, normalize_illust_id

from handler import SyncHandler

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
