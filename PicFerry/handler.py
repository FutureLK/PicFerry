"""PicFerry HTTP 路由层：SyncHandler 全部 /api/* 路由处理 + strip_remote_locked_keys 声明权剥除。"""
import hashlib
import http.server
import json
import mimetypes
import os
import time
import urllib.parse

import logging_util
from logging_util import LOG_BUFFER, LOG_LOCK, console_log
from config_store import load_config, save_config

# 导入期计时(debug 诊断): 与 server.py 导入区同一机制, 数据常驻 logging_util.IMPORT_TIMING
_t_imp = time.perf_counter()
from pathsafety import is_local_path, strip_file_prefix, _safe_error_text, _sanitize_rel_path, _check_local_base, _check_realpath_within, _assert_declared_scan_base
logging_util.IMPORT_TIMING['pathsafety'] = round((time.perf_counter() - _t_imp) * 1000)

_t_imp = time.perf_counter()
from datasources import IMAGE_EXTS, is_ftp, resolve_url, http_fetch, http_put, ftp_list, ftp_upload, parse_html_listing, local_list, _read_remote_file
logging_util.IMPORT_TIMING['datasources'] = round((time.perf_counter() - _t_imp) * 1000)

_t_imp = time.perf_counter()
from webassets import HTML
logging_util.IMPORT_TIMING['webassets'] = round((time.perf_counter() - _t_imp) * 1000)

_t_imp = time.perf_counter()
from pixiv import pixiv_job, _start_pixiv_job, load_blacklist, save_blacklist, normalize_illust_id
logging_util.IMPORT_TIMING['pixiv'] = round((time.perf_counter() - _t_imp) * 1000)

# ─── 声明权控制 ──────────────────────────────────────────────────────────────
# 本地基座声明(dev1ceA/dev1ceB/PixivL 中的本地盘形态)与 PHPSESSID 属本机专属配置,
# 远程来源提交时剥除——防借改写声明基座升级为全盘读写, 防远程清空声明或凭证。
# 远程设备对设备键的合法用途是网络地址(http://、ftp://), 不受影响。

def strip_remote_locked_keys(data: dict):
    """就地剥除 data 中不允许远程写入的键, 返回被剥除的键名列表。
    - dev1ceA/dev1ceB/PixivL: 本地盘形态值与空串(=清除声明)不受理;
    - PHPSESSID: 无论何值均不受理(凭证仅限本机写入/清空)。"""
    removed = []
    for k in ('dev1ceA', 'dev1ceB', 'PixivL'):
        if k not in data:
            continue
        v = data[k]
        if not isinstance(v, str) or not v.strip() or is_local_path(v):
            del data[k]
            removed.append(k)
    if 'PHPSESSID' in data:
        del data['PHPSESSID']
        removed.append('PHPSESSID')
    return removed


# ─── Debug 诊断 ──────────────────────────────────────────────────────────────
# 导入耗时数据在 server.py / handler.py 导入区采集(常驻 logging_util.IMPORT_TIMING);
# debugMode 由关转开时补发, 开关即时生效无需重启。经 logging_util 属性访问只读。

def _emit_import_timing():
    timing = logging_util.IMPORT_TIMING
    total = 0
    for name, ms in timing.items():
        console_log('DEBUG', f'模块导入 {name}: {ms} ms')
        total += ms
    console_log('DEBUG', f'模块导入合计: {total} ms')


class SyncHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    timeout = 60   # 连接读超时(秒): 空闲/慢连接不再无限占用工作线程

    def log_message(self, format, *args):
        pass  # suppress default logging

    def _send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self):
        body = HTML.encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, code=404, msg='Not Found'):
        body = msg.encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'text/plain; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _check_origin(self):
        """同源校验: Origin/Referer 与 Host 不一致即拒绝（防浏览器跨站调用）;
        allowLan=0 时另校验 Host 主机名 ∈ {127.0.0.1, localhost, ::1}（防 DNS rebinding）;
        主机名解析用 urlsplit（正确处理 IPv6 方括号），并小写化、去尾点（Host 大小写/尾点 FQDN 不敏感）;
        无 Origin/Referer 的本地/命令行客户端放行"""
        host = self.headers.get('Host', '')
        if not load_config().get('allowLan'):
            hostname = (urllib.parse.urlsplit('//' + host).hostname or '').lower().rstrip('.')
            if hostname not in ('127.0.0.1', 'localhost', '::1'):
                return False
        origin = self.headers.get('Origin')
        if origin and origin.lower() not in (f'http://{host}'.lower(), f'https://{host}'.lower()):
            return False
        referer = self.headers.get('Referer')
        if referer:
            ref_host = urllib.parse.urlparse(referer).netloc.lower()
            if ref_host and ref_host != host.lower():
                return False
        return True

    def _is_loopback_client(self):
        """客户端是否来自回环地址(决定敏感键的声明权)"""
        ip = self.client_address[0]
        return ip in ('127.0.0.1', '::1') or (isinstance(ip, str) and ip.startswith('::ffff:127.'))

    def do_OPTIONS(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path.startswith('/api/') and not self._check_origin():
            self._send_error(403, 'Forbidden')
            return
        self.send_response(204)
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        if parsed.path.startswith('/api/') and not self._check_origin():
            self._send_error(403, 'Forbidden')
            return

        if parsed.path == '/':
            self._send_html()
        elif parsed.path == '/api/list':
            self._handle_list(params)
        elif parsed.path == '/api/image':
            self._handle_image(params)
        elif parsed.path == '/api/log':
            self._handle_log(params)
        elif parsed.path == '/api/logs':
            self._handle_logs(params)
        elif parsed.path == '/api/pixiv/job':
            self._handle_pixiv_job()
        elif parsed.path == '/api/pixiv/job/result':
            self._handle_pixiv_job_result()
        elif parsed.path == '/api/blacklist':
            self._handle_blacklist()
        elif parsed.path == '/api/config':
            self._handle_config()
        else:
            self._send_error(404)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        if parsed.path.startswith('/api/') and not self._check_origin():
            self._send_error(403, 'Forbidden')
            return

        if parsed.path == '/api/hash':
            self._handle_hash(params)
        elif parsed.path == '/api/copy':
            self._handle_copy(params)
        elif parsed.path == '/api/pixiv/bookmarks':
            self._handle_pixiv_bookmarks()
        elif parsed.path == '/api/pixiv/bookmarks/stop':
            self._handle_pixiv_stop()
        elif parsed.path == '/api/blacklist/add':
            self._handle_blacklist_add()
        elif parsed.path == '/api/blacklist/remove':
            self._handle_blacklist_remove()
        elif parsed.path == '/api/blacklist/clear':
            self._handle_blacklist_clear()
        elif parsed.path == '/api/log':
            self._handle_log(params)
        elif parsed.path == '/api/logs/clear':
            self._handle_logs_clear()
        elif parsed.path == '/api/config/save':
            self._handle_config_save()
        else:
            self._send_error(404)

    def _handle_list(self, params):
        phone_url = params.get('url', [None])[0]
        if not phone_url:
            self._send_json({'error': 'Missing url parameter'})
            return

        try:
            if is_local_path(phone_url):
                _assert_declared_scan_base(phone_url)   # 未声明 → ValueError → 统一错误响应
                files = local_list(phone_url)
                console_log('SCAN', f'本地扫描: {len(files)} 个文件 ({phone_url})')
            elif is_ftp(phone_url):
                entries = ftp_list(phone_url)
                files = [e for e in entries
                         if os.path.splitext(e['name'])[1].lower() in IMAGE_EXTS]
            else:
                body, status = http_fetch(phone_url)
                files = parse_html_listing(body)

            console_log('SCAN', f'成功: {len(files)} 个文件')
            self._send_json({'files': files, 'total': len(files)})
        except Exception as e:
            console_log('ERROR', f'列表请求失败: {phone_url} - {e}')
            self._send_json({'error': _safe_error_text(e), 'files': []})

    def _handle_hash(self, params):
        phone_url = params.get('url', [None])[0]
        filename = params.get('file', [None])[0]
        if not phone_url or not filename:
            self._send_json({'error': 'Missing url or file parameter'})
            return

        try:
            data = _read_remote_file(phone_url, filename)
            h = hashlib.sha256(data).hexdigest()
            self._send_json({'filename': filename, 'sha256': h})
        except Exception as e:
            console_log('ERROR', f'哈希失败: {filename} - {e}')
            self._send_json({'error': _safe_error_text(e)})

    def _handle_copy(self, params):
        from_url = params.get('from', [None])[0]
        to_url = params.get('to', [None])[0]
        filename = params.get('file', [None])[0]

        if not from_url or not to_url or not filename:
            self._send_json({'success': False, 'error': 'Missing parameters'})
            return

        try:
            filename = _sanitize_rel_path(filename)
            data = _read_remote_file(from_url, filename)

            if is_local_path(to_url):
                base = strip_file_prefix(to_url)
                _check_local_base(base)
                dst = os.path.join(base, filename)
                _check_realpath_within(base, dst)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                with open(dst, 'wb') as f:
                    f.write(data)
            elif is_ftp(to_url):
                ftp_upload(to_url, filename, data)
            else:
                dst_url = resolve_url(to_url, filename)
                http_put(dst_url, data)

            size_kb = len(data) / 1024
            console_log('SYNC', f'完成: {filename} ({size_kb:.1f} KB)')
            self._send_json({'success': True, 'filename': filename})
        except Exception as e:
            console_log('ERROR', f'同步失败: {filename} - {e}')
            self._send_json({'success': False, 'filename': filename, 'error': _safe_error_text(e)})

    def _handle_pixiv_bookmarks(self):
        """POST /api/pixiv/bookmarks: 同步校验 → 后台启动 Job → 立即返回。
        原同步实现已迁移到 run_pixiv_job（fetching→scanning→matching→done）。"""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length == 0:
                self._send_json({'error': 'Empty request body'})
                return
            body = self.rfile.read(content_length)
            req_data = json.loads(body)
        except Exception as e:
            console_log('ERROR', f'Pixiv 请求体解析失败: {e}')
            self._send_json({'error': f'Invalid request body: {e}'})
            return

        uid = str(req_data.get('uid', '')).strip()
        phpsessid = str(req_data.get('phpsessid', '')).strip() or ('' if load_config().get('allowLan') else load_config().get('PHPSESSID', ''))
        local_path = str(req_data.get('path', '')).strip()

        if not uid or not phpsessid:
            self._send_json({'error': '请填写 Pixiv UID 和 PHPSESSID'})
            return
        if not local_path:
            self._send_json({'error': '请填写本地文件夹路径'})
            return

        try:
            limit = int(req_data['limit']) if 'limit' in req_data else load_config().get('pixivLimit', 0)
        except (TypeError, ValueError):
            limit = load_config().get('pixivLimit', 0)

        ok, msg = _start_pixiv_job(uid, phpsessid, local_path, limit)
        if not ok:
            self._send_json({'error': msg})
            return
        console_log('SCAN', f'Pixiv: 开始拉取收藏 (UID={uid}, limit={limit})')
        self._send_json({'ok': True, 'status': 'fetching'})

    def _handle_pixiv_stop(self):
        """POST /api/pixiv/bookmarks/stop: 置 stop 事件, Job 在下个检查点停止;
        仅限本机调用——防局域网内任意设备终止他方启动的扫描任务"""
        if not self._is_loopback_client():
            console_log('INFO', '远程来源请求终止 Pixiv 任务, 已拒绝')
            self._send_json({'error': '终止操作仅限本机'})
            return
        pixiv_job['stop'].set()
        self._send_json({'ok': True})

    def _handle_pixiv_job(self):
        """GET /api/pixiv/job: 轻量状态轮询（不含 result 数组）"""
        with pixiv_job['lock']:
            status = pixiv_job['status']
            progress = dict(pixiv_job['progress'])
            error = pixiv_job['error']
            summary = pixiv_job['summary']
        self._send_json({'status': status, 'progress': progress, 'error': error, 'summary': summary})

    def _handle_pixiv_job_result(self):
        """GET /api/pixiv/job/result: 仅 done 时返回 matched 数组"""
        with pixiv_job['lock']:
            result = pixiv_job['result'] if pixiv_job['status'] == 'done' else []
        self._send_json({'matched': result})

    def _handle_blacklist(self):
        """GET /api/blacklist: 返回已排序 id 列表"""
        self._send_json({'ids': sorted(load_blacklist())})

    def _handle_blacklist_add(self):
        """POST /api/blacklist/add: 支持裸 ID 与 /artworks/ 链接"""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length == 0:
                self._send_json({'error': 'Empty request body'})
                return
            body = self.rfile.read(content_length)
            req_data = json.loads(body)
        except Exception as e:
            console_log('ERROR', f'黑名单请求体解析失败: {e}')
            self._send_json({'error': f'Invalid request body: {e}'})
            return
        nid = normalize_illust_id(req_data.get('id', ''))
        if not nid:
            self._send_json({'error': '无法识别的作品 ID'})
            return
        ids = load_blacklist()
        ids.add(nid)
        if not save_blacklist(ids):
            console_log('ERROR', '黑名单保存失败')
            self._send_json({'ok': False, 'error': '黑名单保存失败'})
            return
        console_log('BLACKLIST', f'Pixiv: 黑名单添加 {nid} (共 {len(ids)} 个)')
        self._send_json({'ok': True})

    def _handle_blacklist_remove(self):
        """POST /api/blacklist/remove"""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length == 0:
                self._send_json({'error': 'Empty request body'})
                return
            body = self.rfile.read(content_length)
            req_data = json.loads(body)
        except Exception as e:
            console_log('ERROR', f'黑名单请求体解析失败: {e}')
            self._send_json({'error': f'Invalid request body: {e}'})
            return
        nid = normalize_illust_id(req_data.get('id', ''))
        if not nid:
            self._send_json({'error': '无法识别的作品 ID'})
            return
        ids = load_blacklist()
        ids.discard(nid)
        if not save_blacklist(ids):
            console_log('ERROR', '黑名单保存失败')
            self._send_json({'ok': False, 'error': '黑名单保存失败'})
            return
        console_log('BLACKLIST', f'Pixiv: 黑名单移除 {nid} (剩 {len(ids)} 个)')
        self._send_json({'ok': True})

    def _handle_blacklist_clear(self):
        """POST /api/blacklist/clear: 保存空集"""
        if not save_blacklist(set()):
            console_log('ERROR', '黑名单保存失败')
            self._send_json({'ok': False, 'error': '黑名单保存失败'})
            return
        console_log('BLACKLIST', 'Pixiv: 黑名单已清空')
        self._send_json({'ok': True})

    def _handle_image(self, params):
        phone_url = params.get('url', [None])[0]
        filename = params.get('file', [None])[0]
        if not phone_url or not filename:
            self._send_error(400, 'Missing parameters')
            return

        try:
            data = _read_remote_file(phone_url, filename)

            ext = os.path.splitext(filename)[1].lower()
            ct = mimetypes.types_map.get(ext, 'application/octet-stream')

            self.send_response(200)
            self.send_header('Content-Type', ct)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'public, max-age=3600')
            self.end_headers()
            self.wfile.write(data)
        except Exception as e:
            console_log('ERROR', f'图片加载失败: {filename} - {e}')
            self._send_error(404, '图片加载失败')

    def _handle_log(self, params):
        msg = params.get('msg', [None])[0]
        cat = params.get('cat', ['INFO'])[0]
        if msg:
            # 截断优于拒绝: 防超长外文挤占 500 条环形缓冲(截断后前端无感)
            console_log(cat[:32], msg[:512])
        self._send_json({'ok': True})

    def _handle_logs(self, params):
        """GET /api/logs?since=<int>: 增量返回缓冲日志; truncated 统一语义:
        since > 0 且（缓冲为空 或 最早条目 id > since 或 since > next_id）"""
        try:
            since = int(params.get('since', ['0'])[0])
        except (TypeError, ValueError):
            since = 0
        with LOG_LOCK:
            items = list(LOG_BUFFER)
            next_id = logging_util.LOG_LAST_ID
            truncated = since > 0 and (
                len(items) == 0 or items[0][0] > since or since > next_id
            )
            logs = [{'id': i, 'ts': t, 'cat': c, 'msg': m}
                    for i, t, c, m in items if i > since]
        self._send_json({'logs': logs, 'next_id': next_id, 'truncated': truncated})

    def _handle_logs_clear(self):
        """POST /api/logs/clear: 只清内存缓冲, 计数器不重置"""
        with LOG_LOCK:
            LOG_BUFFER.clear()
        self._send_json({'ok': True})

    def _handle_config(self):
        conf = load_config()
        conf['hasPhpsessid'] = bool(conf.get('PHPSESSID'))
        conf['PHPSESSID'] = ''
        self._send_json(conf)

    def _handle_config_save(self):
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            data = json.loads(body)
            if not self._is_loopback_client():
                dropped = strip_remote_locked_keys(data)
                if dropped:
                    console_log('INFO', f'远程提交已忽略本机专属键: {",".join(dropped)}')
            # debug 关→开检测: 保存前取旧值, 保存后回读新值(两次串行 load_config, 不嵌套持锁)
            debug_prev = bool(load_config().get('debugMode')) if 'debugMode' in data else None
            if not save_config(data):
                # 文件损坏拒绝覆盖(防凭证被默认值抹除) / 写盘失败
                self._send_json({'error': '配置未保存：config.ini 损坏或写入失败，见服务端日志'})
                return
            if debug_prev is False and bool(load_config().get('debugMode')):
                _emit_import_timing()
            self._send_json({'ok': True})
        except Exception as e:
            console_log('ERROR', f'配置保存失败: {e}')
            self._send_json({'error': f'保存失败: {e}'})
