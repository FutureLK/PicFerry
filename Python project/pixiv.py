# PicFerry 机械拆分模块: 本文件代码由 server.py 原样移入（Pixiv 查重: 黑名单/收藏拉取/后台 Job 引擎）, 纯移动, 零逻辑改动。
import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from config_store import CONFIG_DIR, load_config
from logging_util import console_log
from pathsafety import is_local_path, _safe_error_text, _assert_declared_scan_base
from datasources import IMAGE_EXTS, is_ftp, ftp_list, http_fetch, parse_html_listing, local_list


PIXIV_BOOKMARK_URL = 'https://www.pixiv.net/ajax/user/{uid}/illusts/bookmarks'
PIXIV_REFERER = 'https://www.pixiv.net/'
PIXIV_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'

# ─── Pixiv 查重黑名单 (blacklist.csv) ────────────────────────────────────────
# 格式: 表头 "illust_id" + 每行一个作品 ID。表头行预留扩展列（如 tag/user_id）空间。
BLACKLIST_PATH = os.path.join(CONFIG_DIR, 'blacklist.csv')
BLACKLIST_LOCK = threading.Lock()


def load_blacklist():
    """读黑名单集合; 文件缺失时【创建】含表头 'illust_id' 的空文件并返回空 set。
    文件创建是 load 的职责（GET /api/blacklist 与 Job 启动都会触发）。"""
    with BLACKLIST_LOCK:
        ids = set()
        try:
            with open(BLACKLIST_PATH, encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line == 'illust_id':
                        continue
                    ids.add(line)
        except FileNotFoundError:
            try:
                with open(BLACKLIST_PATH, 'w', encoding='utf-8') as f:
                    f.write('illust_id\n')
            except OSError:
                pass
        except OSError:
            pass
        return ids


def save_blacklist(ids):
    """原子写: 临时文件 + os.replace, 避免并发读看到半写文件; 返回是否成功"""
    with BLACKLIST_LOCK:
        tmp = BLACKLIST_PATH + '.tmp'
        try:
            with open(tmp, 'w', encoding='utf-8') as f:
                f.write('illust_id\n')
                for i in sorted(ids):
                    f.write(i + '\n')
            os.replace(tmp, BLACKLIST_PATH)
            return True
        except OSError:
            try:
                os.remove(tmp)
            except OSError:
                pass
            return False


def normalize_illust_id(raw):
    """输入可为纯数字 '123' 或作品链接 'https://www.pixiv.net/artworks/123' → 返回 '123';
    无法提取时返回 None。"""
    if raw is None:
        return None
    s = str(raw).strip()
    m = re.search(r'/artworks/(\d+)', s)
    if m:
        return m.group(1)
    if s.isdigit():
        return s
    return None


def blacklist_snapshot():
    """返回当前黑名单集合的副本（Job 启动时取快照, 运行中编辑不影响本次扫描）"""
    return set(load_blacklist())

def fetch_all_pixiv_bookmark_ids(uid, phpsessid, limit=0, stop_event=None, blacklist=None, interval=0.8):
    """拉取全部收藏 (public + private), 返回 {str(id): int(pageCount)}。

    - limit: 0=全部; 否则累计【非黑名单】ID 数达到 limit 即停（show 流先取, hide 流补足）
    - stop_event: 每页请求后检查, 已置位则提前返回已收集部分
    - blacklist: 拉取循环内跳过并累计计数, 不计入 limit 预算
    - interval: 请求间隔（秒, 默认 0.8）
    """
    bookmarks = {}
    blacklist = blacklist or set()
    request_count = 0
    skipped_total = 0
    stream_totals = {}   # visibility -> 该流 total（首页返回后可知）

    def known_total():
        return sum(stream_totals.values())

    def update_progress():
        denom = min(limit, known_total()) if limit > 0 else known_total()
        with pixiv_job['lock']:
            pixiv_job['progress'] = {'phase': 'fetching',
                                     'fetched': len(bookmarks), 'total': denom or 0}

    for visibility in ('show', 'hide'):
        offset = 0
        page_size = 100

        while True:
            if stop_event is not None and stop_event.is_set():
                return bookmarks

            params = urllib.parse.urlencode({
                'tag': '', 'offset': offset, 'limit': page_size, 'rest': visibility
            })
            full_url = PIXIV_BOOKMARK_URL.format(uid=uid) + '?' + params

            req = urllib.request.Request(full_url)
            req.add_header('Cookie', 'PHPSESSID=' + phpsessid)
            req.add_header('Referer', PIXIV_REFERER)
            req.add_header('User-Agent', PIXIV_UA)

            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode('utf-8'))

            if data.get('error'):
                raise Exception(f'Pixiv API error: {data.get("body", "Unknown")}')

            works = data.get('body', {}).get('works', [])
            stream_total = data.get('body', {}).get('total', 0)
            stream_totals[visibility] = stream_total
            if not works:
                break

            # 页内批量: 提取 id+pageCount, 剔除黑名单（filter_blacklisted 纯函数在此共用）
            batch = {}
            for work in works:
                wid = str(work.get('id', ''))
                if wid:
                    batch[wid] = int(work.get('pageCount') or 1)
            before = len(batch)
            batch = filter_blacklisted(batch, blacklist)
            skipped_total += before - len(batch)

            # limit 预算: 非黑名单累计数达标即停（页内截断, 提前返回）
            if limit and limit > 0:
                remaining = limit - len(bookmarks)
                if remaining <= 0:
                    return bookmarks
                if len(batch) > remaining:
                    batch = dict(list(batch.items())[:remaining])

            for wid, page_count in batch.items():
                if wid not in bookmarks:
                    bookmarks[wid] = page_count

            request_count += 1
            skip_note = f' 黑名单跳过{skipped_total}' if skipped_total else ''
            console_log('SCAN', f'Pixiv({visibility}): {len(bookmarks)}/{stream_total} 请求{request_count}次{skip_note}')
            update_progress()

            offset += page_size
            if offset >= stream_total:
                break

            time.sleep(max(0.1, interval))  # rate limit (可配置)

    return bookmarks


def is_page_covered(illust_id, page, bookmarks):
    """分p存在性匹配: 本地文件 illust_id_pN 仅当书签 pageCount > N 判定已收藏 (分页 0-indexed)"""
    page_count = bookmarks.get(illust_id)
    if page_count is None:
        return False
    return page < page_count


def filter_blacklisted(bookmarks, blacklist):
    """返回剔除黑名单 ID 后的 {id: pageCount} 副本（fetch 循环与单元测试共用）"""
    return {i: c for i, c in bookmarks.items() if i not in blacklist}


def extract_illust_page(filename):
    """返回 (illust_id, page); 无 _pN 后缀的文件按 page=0。按 basename 匹配, 支持子目录相对路径。"""
    base = os.path.basename(filename)
    m = re.match(r'^(\d+)_p(\d+)', base)
    if m:
        return m.group(1), int(m.group(2))
    m2 = re.match(r'^(\d+)', base)
    if m2:
        return m2.group(1), 0
    return None, None


# ─── Pixiv 后台 Job 引擎（单槽: 可终止/限量/进度）─────────────────────────────

pixiv_job = {
    'status': 'idle',            # idle|fetching|scanning|matching|done|stopped|error
    'thread': None,
    'stop': threading.Event(),
    'lock': threading.Lock(),
    'progress': {'phase': '', 'fetched': 0, 'total': 0},
    'summary': None,             # done 时: {total_bookmarks, local_count, missing_works, missing_pages}
    'error': None,
    'result': None,              # done 时: matched 数组
}


def _scan_local_files(path):
    """扫描本地目录/FTP/HTTP 源, 返回 [{name, size}]（保持原 _handle_pixiv_bookmarks 的扫描方式）
    本地路径未在 config 中声明时抛 ValueError → 上层记为 Job error 态"""
    if is_local_path(path):
        _assert_declared_scan_base(path)
        return local_list(path)
    if is_ftp(path):
        entries = ftp_list(path)
        return [e for e in entries
                if os.path.splitext(e['name'])[1].lower() in IMAGE_EXTS]
    body_text, status = http_fetch(path)
    return parse_html_listing(body_text)


def run_pixiv_job(uid, phpsessid, path, limit=0, fetch_fn=fetch_all_pixiv_bookmark_ids, local_scan_fn=None):
    """由 job 线程调用（也可同步调用做单元测试）:
    状态机 fetching→scanning→matching→done / stopped / error。
    关键时序约束: fetch_fn 返回后【立即先检查 stop】再处理结果 —— 顺序不可颠倒;
    阶段切换点 (fetching→scanning→matching) 处【先检查 stop 再进入昂贵阶段】(如本地扫描)。"""
    conf = load_config()
    interval = conf.get('pixivInterval', 0.8)
    max_rows = conf.get('maxRows', 1000)

    # 黑名单快照: 启动时取一次, 运行中的黑名单编辑不影响本次扫描
    blacklist = blacklist_snapshot()

    def set_state(**updates):
        with pixiv_job['lock']:
            for k, v in updates.items():
                pixiv_job[k] = v

    try:
        # ── fetching ──
        set_state(status='fetching', error=None, summary=None, result=None,
                  progress={'phase': 'fetching', 'fetched': 0, 'total': 0})
        try:
            bookmarks = fetch_fn(uid, phpsessid, limit, pixiv_job['stop'], blacklist, interval)
        except urllib.error.HTTPError as e:
            if e.code == 403:
                raise RuntimeError('Pixiv 认证失败，请检查 PHPSESSID 是否有效或已过期') from e
            if e.code == 404:
                raise RuntimeError('Pixiv 用户不存在，请检查 UID') from e
            raise RuntimeError(f'HTTP {e.code}') from e
        if pixiv_job['stop'].is_set():          # 先查 stop, 再处理结果 —— 顺序不可颠倒
            set_state(status='stopped')
            return
        total_fetch = len(bookmarks) if limit == 0 else min(limit, len(bookmarks))
        set_state(progress={'phase': 'fetching', 'fetched': len(bookmarks), 'total': total_fetch})

        # ── scanning ──
        if pixiv_job['stop'].is_set():
            set_state(status='stopped')
            return
        set_state(status='scanning', progress={'phase': 'scanning', 'fetched': 0, 'total': 0})
        local_files = local_scan_fn(path) if local_scan_fn else _scan_local_files(path)
        if pixiv_job['stop'].is_set():
            set_state(status='stopped')
            return

        # ── matching（反转: 以收藏作品为粒度, 统计本地缺失分p）──
        if pixiv_job['stop'].is_set():
            set_state(status='stopped')
            return
        set_state(status='matching', progress={'phase': 'matching', 'fetched': 0, 'total': len(bookmarks)})
        saved = {}
        for f in local_files:
            if pixiv_job['stop'].is_set():
                set_state(status='stopped')
                return
            illust_id, page = extract_illust_page(f['name'])
            if not illust_id:
                continue
            page_count = bookmarks.get(illust_id)
            if page_count is None:
                continue
            if is_page_covered(illust_id, page, bookmarks):   # 匹配判定不变 (page < pageCount)
                saved.setdefault(illust_id, set()).add(page)
            set_state(progress={'phase': 'matching', 'fetched': len(saved), 'total': len(bookmarks)})

        # 缺失作品聚合（默认 illust_id 数值升序; 排序方式可调整）
        missing = []
        for wid, page_count in sorted(bookmarks.items(), key=lambda kv: int(kv[0])):
            if pixiv_job['stop'].is_set():
                set_state(status='stopped')
                return
            x = len(saved.get(wid, set()))
            if x < page_count:
                missing.append({
                    'illust_id': wid,
                    'pageCount': page_count,
                    'saved_pages': x,
                    'missing_pages': page_count - x,
                    'range': 'p0~p' + str(page_count - 1),
                })
        missing_works_total = len(missing)          # 截断前统计
        missing_pages_total = sum(m['missing_pages'] for m in missing)
        missing = missing[:max_rows]                # max_rows 按作品数截断
        set_state(status='done',
                  progress={'phase': 'done', 'fetched': len(missing), 'total': len(missing)},
                  summary={'total_bookmarks': len(bookmarks),
                           'local_count': len(local_files),
                           'missing_works': missing_works_total,
                           'missing_pages': missing_pages_total},
                  result=missing)
    except Exception as e:
        console_log('ERROR', f'Pixiv 查重失败: {e}')
        # 入库前脱敏: OS 异常原文含引号本地路径/file: 前缀, 不应经轮询端点发往局域网
        set_state(status='error', error=_safe_error_text(e))


def _start_pixiv_job(uid, phpsessid, path, limit=0):
    """原子 check-and-set 启动单槽任务; 返回 (ok, message)"""
    with pixiv_job['lock']:
        if pixiv_job['status'] not in ('idle', 'done', 'stopped', 'error') or (
                pixiv_job['thread'] and pixiv_job['thread'].is_alive()):
            return False, '已有任务在运行'
        pixiv_job['stop'].clear()      # 必须清除遗留 stop, 否则新任务在首个检查点立即停止
        pixiv_job['status'] = 'fetching'
        pixiv_job['progress'] = {'phase': 'fetching', 'fetched': 0, 'total': 0}
        pixiv_job['summary'] = None
        pixiv_job['error'] = None
        pixiv_job['result'] = None
        t = threading.Thread(target=run_pixiv_job, args=(uid, phpsessid, path, limit), daemon=True)
        pixiv_job['thread'] = t
        t.start()
    return True, 'fetching'
