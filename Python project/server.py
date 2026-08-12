"""
图片同步 - 局域网文件比对与传输
跨设备图片同步工具，支持 HTTP/FTP 协议
"""

import http.server
import json
import urllib.request
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
import time
import mimetypes
import configparser
import itertools

PORT = 13826
IMAGE_EXTS = ('.jpg', '.jpeg', '.png', '.gif', '.webp')

# ─── Config ──────────────────────────────────────────────────────────────────

# 注意: 必须在【模块级】捕获脚本目录 —— 函数体内 dir() 只返回局部作用域,
# 看不到模块级 __file__, 因此不能在 runtime_dir() 内部判断 '__file__' in dir()。
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__)) if '__file__' in dir() else os.getcwd()

def runtime_dir():
    """EXE 模式下返回 EXE 所在目录, 源码模式返回 server.py 所在目录"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return _SCRIPT_DIR

CONFIG_PATH = os.path.join(runtime_dir(), 'config.ini')

# 新设置键: 默认值与范围 (key: (default, lo, hi, type))
_CONFIG_KEYS = {
    'thumbnailSize':  (48,   16,    128,    'int'),    # px
    'previewDelay':   (500,  100,   2000,   'int'),    # ms
    'pixivInterval':  (0.8,  0.1,   10,     'float'),  # s
    'pixivLimit':     (0,    0,     100000, 'int'),    # 0=全部
    'maxRows':        (1000, 10,    5000,   'int'),    # 行数上限
}

def _parse_config_value(key, raw):
    """解析配置值: 空串/非数字回落默认值, 越界钳制; 返回规范类型"""
    default, lo, hi, vtype = _CONFIG_KEYS[key]
    try:
        if vtype == 'float':
            val = float(str(raw).strip())
        else:
            val = int(float(str(raw).strip()))
        return max(lo, min(hi, val))
    except (TypeError, ValueError):
        return default

def load_config():
    cfg = configparser.ConfigParser()
    cfg.read(CONFIG_PATH, encoding='utf-8')
    conf = {
        'dev1ceA': cfg.get('Settings', 'dev1ceA', fallback=''),
        'dev1ceB': cfg.get('Settings', 'dev1ceB', fallback=''),
        'PixivUID': cfg.get('Settings', 'PixivUID', fallback=''),
        'PHPSESSID': cfg.get('Settings', 'PHPSESSID', fallback=''),
        'PixivL': cfg.get('Settings', 'PixivL', fallback=''),
    }
    for key in _CONFIG_KEYS:
        conf[key] = _parse_config_value(key, cfg.get('Settings', key, fallback=''))
    return conf

def save_config(data: dict):
    keys = ['dev1ceA', 'dev1ceB', 'PixivUID', 'PHPSESSID', 'PixivL'] + list(_CONFIG_KEYS.keys())
    lines = ['[Settings]\n']
    for k in keys:
        if k in _CONFIG_KEYS:
            default, _, _, _ = _CONFIG_KEYS[k]
            v = _parse_config_value(k, data.get(k, default))
            lines.append(f'{k} = {v}\n')
        else:
            v = data.get(k, '')
            lines.append(f'{k} = {v}\n')
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        f.writelines(lines)

# ─── Console logging ─────────────────────────────────────────────────────────

LOG_COLORS = {
    'SCAN': '\033[96m',    # cyan
    'HASH': '\033[93m',    # yellow
    'SYNC': '\033[94m',    # blue
    'IMAGE': '\033[90m',   # grey
    'DONE': '\033[92m',    # green
    'ERROR': '\033[91m',   # red
}
RESET = '\033[0m'

# ─── 内存日志环形缓冲（供网页日志面板轮询）─────────────────────────────────
import collections
import threading

LOG_BUFFER = collections.deque(maxlen=500)
LOG_SEQ = itertools.count(1)   # 单调 id; 进程存活期内不回退, 清空不重置
LOG_LAST_ID = 0                # 已发出的最大 id（itertools.count 不可回读, 单独维护）
LOG_LOCK = threading.Lock()

# 检测终端是否支持 ANSI 颜色（Windows 旧终端可能不支持）
_USE_COLOR = True
try:
    import platform
    if platform.system() == 'Windows':
        ver = platform.version().split('.')
        major = int(ver[0]) if ver else 0
        if major < 10:
            _USE_COLOR = False
except:
    pass

def console_log(category, message):
    ts = datetime.datetime.now().strftime('%H:%M:%S')
    line = f'[{ts}] [{category}] {message}'

    # 写日志文件（EXE 所在目录）
    try:
        log_dir = runtime_dir()
        with open(os.path.join(log_dir, 'sync.log'), 'a', encoding='utf-8') as f:
            f.write(f'{line}\n')
    except:
        pass

    # 写控制台 stderr（比 stdout 更可靠，在 PyInstaller 下也不会被吞）
    try:
        if _USE_COLOR:
            color = LOG_COLORS.get(category, '')
            sys.stderr.write(f' {color}{line}{RESET}\n')
        else:
            sys.stderr.write(f' {line}\n')
        sys.stderr.flush()
    except:
        pass

    # 写内存环形缓冲（供网页日志面板增量轮询）; 存原始分类与消息, 不含 ANSI
    try:
        global LOG_LAST_ID
        log_id = next(LOG_SEQ)
        with LOG_LOCK:
            LOG_LAST_ID = log_id
            LOG_BUFFER.append((log_id, ts, category, message))
    except:
        pass

# ─── Embedded HTML ───────────────────────────────────────────────────────────

HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>图片同步</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#0d1117;color:#c9d1d9;min-height:100vh}
.container{max-width:960px;margin:0 auto;padding:24px 16px}
h1{font-size:22px;font-weight:600;color:#e6edf3;margin-bottom:4px}
.subtitle{font-size:13px;color:#8b949e;margin-bottom:24px}
.card{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:20px;margin-bottom:16px}
.card-title{font-size:13px;font-weight:600;color:#8b949e;margin-bottom:12px;letter-spacing:.3px}
.input-group{margin-bottom:12px}
.input-group:last-child{margin-bottom:0}
.input-group label{display:block;font-size:13px;color:#8b949e;margin-bottom:4px;font-weight:500}
.input-group input[type="text"]{width:100%;padding:10px 12px;background:#0d1117;border:1px solid #30363d;border-radius:6px;color:#c9d1d9;font-size:14px;font-family:inherit;outline:none;transition:border-color .2s}
.input-group input[type="text"]:focus{border-color:#58a6ff}
.input-group input[type="text"]::placeholder{color:#484f58}
.input-group input[type="password"]{width:100%;padding:10px 12px;background:#0d1117;border:1px solid #30363d;border-radius:6px;color:#c9d1d9;font-size:14px;font-family:inherit;outline:none;transition:border-color .2s}
.input-group input[type="password"]:focus{border-color:#58a6ff}
.input-group input[type="password"]::placeholder{color:#484f58}
.actions{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:16px}
.btn{display:inline-flex;align-items:center;gap:6px;padding:10px 20px;border:none;border-radius:6px;font-size:14px;font-weight:500;cursor:pointer;transition:all .2s;font-family:inherit}
.btn:disabled{opacity:.5;cursor:not-allowed}
.btn-primary{background:#238636;color:#fff}
.btn-primary:hover:not(:disabled){background:#2ea043}
.btn-danger{background:#da3633;color:#fff}
.btn-danger:hover:not(:disabled){background:#f85149}
.btn:active:not(:disabled){transform:scale(.97)}
.toggle-group{display:flex;align-items:center;gap:8px;font-size:13px;color:#8b949e;cursor:pointer;user-select:none;padding:6px 12px;background:#21262d;border-radius:6px;border:1px solid #30363d}
.toggle-group input[type="checkbox"]{width:16px;height:16px;accent-color:#58a6ff;cursor:pointer}
.status{min-height:24px;font-size:14px;color:#8b949e;margin-bottom:12px;padding:8px 12px;background:#0d1117;border-radius:6px;border:1px solid #30363d;transition:color .3s,border-color .3s}
.status.success{color:#3fb950;border-color:#238636}
.status.error{color:#f85149;border-color:#da3633}
.status.loading{color:#58a6ff;border-color:#58a6ff}
.table-wrap{overflow-x:auto;border:1px solid #30363d;border-radius:6px}
table{width:100%;border-collapse:collapse;font-size:13px}
thead{background:#21262d}
th{text-align:left;padding:10px 12px;color:#8b949e;font-weight:600;border-bottom:1px solid #30363d;white-space:nowrap}
td{padding:8px 12px;border-bottom:1px solid #21262d;vertical-align:middle}
tr:last-child td{border-bottom:none}
tr:hover td{background:#1c2128}
.filename{font-family:'SFMono-Regular',Consolas,'Liberation Mono',Menlo,monospace;font-size:13px;word-break:break-all}
.file-hash{font-family:'SFMono-Regular',Consolas,'Liberation Mono',Menlo,monospace;font-size:11px;color:#8b949e}
.summary{font-size:14px;color:#c9d1d9;margin-bottom:12px;padding:12px 16px;background:#0d1117;border-radius:6px;border:1px solid #30363d;text-align:center}
.progress{background:#0d1117;border-radius:6px;padding:12px 16px;margin-bottom:12px;border:1px solid #30363d;display:none}
.progress.active{display:block}
.progress-bar{height:6px;background:#21262d;border-radius:3px;overflow:hidden;margin-bottom:8px}
.progress-bar-fill{height:100%;background:#238636;width:0%;transition:width .3s;border-radius:3px}
.progress-text{font-size:13px;color:#8b949e}
.empty-state{text-align:center;padding:40px 20px;color:#484f58;font-size:14px}
.input-hint{font-size:12px;color:#484f58;margin-top:2px}
.input-badge{font-size:11px;margin-top:2px;color:#484f58;min-height:14px}
.input-badge.http{color:#58a6ff}
.input-badge.ftp{color:#d29922}
.input-badge.local{color:#3fb950}
.input-badge.invalid{color:#f85149}
.input-badge.error{color:#f85149}
.input-badge.success{color:#3fb950}
/* ─── Stats bar ─── */
.stats{display:flex;gap:16px;margin-bottom:12px;flex-wrap:wrap}
.stat-item{flex:1;min-width:180px;background:#0d1117;border:1px solid #30363d;border-radius:6px;padding:10px 14px}
.stat-label{font-size:11px;color:#8b949e;margin-bottom:2px;letter-spacing:.3px}
.stat-value{font-size:18px;font-weight:600;color:#e6edf3}
.stat-sub{font-size:12px;color:#484f58;margin-top:2px}
/* ─── Direction toggle ─── */
.dir-group{display:flex;background:#21262d;border:1px solid #30363d;border-radius:6px;overflow:hidden}
.dir-btn{padding:8px 16px;font-size:13px;border:none;background:transparent;color:#8b949e;cursor:pointer;font-family:inherit;transition:all .2s}
.dir-btn.active{background:#1f6feb;color:#fff}
.dir-btn:not(.active):hover{color:#c9d1d9}
.dir-btn:first-child{border-right:1px solid #30363d}
#syncBtn{margin-top:12px}
.hidden{display:none}
input[type="checkbox"]{accent-color:#58a6ff;cursor:pointer}
/* ─── Tabs ─── */
.tabs{display:flex;gap:4px;margin-bottom:16px;border-bottom:1px solid #30363d;flex-wrap:wrap}
.tab-btn{padding:8px 18px;font-size:13px;border:none;background:transparent;color:#8b949e;cursor:pointer;font-family:inherit;border-bottom:2px solid transparent;transition:all .2s}
.tab-btn:hover{color:#c9d1d9}
.tab-btn.active{color:#e6edf3;border-bottom-color:#58a6ff}
.tab-panel{display:none}
.tab-panel.active{display:block}
/* ─── Thumbnail ─── */
.thumb-wrap{width:var(--thumb-size,48px);height:var(--thumb-size,48px);flex-shrink:0}
.thumb{width:var(--thumb-size,48px);height:var(--thumb-size,48px);object-fit:cover;border-radius:4px;display:block;background:#0d1117}
.thumb-placeholder{width:48px;height:48px;border-radius:4px;background:#21262d;display:flex;align-items:center;justify-content:center;font-size:16px;color:#484f58}
/* ─── Preview panel ─── */
.preview-panel{display:none;position:fixed;z-index:1000;background:#161b22;border:1px solid #30363d;border-radius:8px;box-shadow:0 8px 32px rgba(0,0,0,.6);overflow:hidden;pointer-events:none;max-width:420px}
.preview-panel.active{display:block}
.preview-panel img{display:block;max-width:400px;max-height:480px;object-fit:contain}
.preview-panel .preview-name{padding:8px 12px;font-size:12px;color:#8b949e;border-top:1px solid #30363d;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
/* ─── Animations ─── */
@keyframes fadeIn{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:translateY(0)}}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.5}}
@keyframes slideDown{from{opacity:0;transform:translateY(-10px)}to{opacity:1;transform:translateY(0)}}
@keyframes fillBar{from{width:0%}to{width:var(--target)}}
.fade-in{animation:fadeIn .35s ease-out both}
.pulse{animation:pulse 2s ease-in-out infinite}
.slide-down{animation:slideDown .3s ease-out forwards}
.fill-bar{animation:fillBar .6s ease-out forwards}
tr.row-enter{animation:fadeIn .35s ease-out both}
/* ─── Help tooltips ─── */
.help-toggle{display:inline-flex;align-items:center;justify-content:center;width:18px;height:18px;border-radius:50%;background:#30363d;color:#8b949e;font-size:11px;cursor:pointer;margin-left:4px;transition:all .2s;vertical-align:middle;line-height:18px;font-style:normal;font-weight:600}
.help-toggle:hover{background:#1f6feb;color:#fff}
.help-text{font-size:12px;color:#8b949e;background:#0d1117;border:1px solid #30363d;border-radius:6px;padding:8px 12px;margin-top:4px;line-height:1.7}
.help-text code{background:#21262d;padding:1px 5px;border-radius:3px;font-size:11px;color:#c9d1d9}
.help-text ol{margin:4px 0 0 18px;padding:0}
.help-text li{margin-bottom:3px}
.pixiv-status{font-size:13px;color:#8b949e;margin-left:12px;transition:color .2s}
.pixiv-status.loading{color:#58a6ff}
.pixiv-status.success{color:#3fb950}
.pixiv-status.error{color:#f85149}
.pixiv-stats{display:flex;gap:16px;padding:10px 14px;background:#0d1117;border:1px solid #30363d;border-radius:6px;font-size:13px;color:#8b949e;flex-wrap:wrap;margin-top:12px}
.pixiv-stats strong{color:#e6edf3;font-weight:600}
/* ─── Log panel ─── */
.log-line{display:block;white-space:pre-wrap;word-break:break-all}
.log-line .cat-SCAN{color:#39c5cf}
.log-line .cat-HASH{color:#d29922}
.log-line .cat-SYNC{color:#58a6ff}
.log-line .cat-IMAGE{color:#8b949e}
.log-line .cat-DONE{color:#3fb950}
.log-line .cat-ERROR{color:#f85149}
.log-line .cat-INFO{color:#c9d1d9}
</style>
</head>
<body>
<div class="container">
  <h1>图片同步</h1>
  <div class="subtitle">局域网文件比对与传输</div>

  <nav class="tabs" id="tabBar"></nav>

  <!-- ═══ 设备连接 ═══ -->
  <section class="tab-panel" id="tab-device">
  <div class="card">
    <div class="input-group">
      <label for="urlA">设备 A（接收端）</label>
      <input type="text" id="urlA" placeholder="http://192.168.1.100:1234/DCIM/Pixez/">
      <div class="input-badge" id="badge-urlA"></div>
    </div>
    <div class="input-group">
      <label for="urlB">设备 B（来源端）</label>
      <input type="text" id="urlB" placeholder="http://192.168.1.101:1234/DCIM/">
      <div class="input-badge" id="badge-urlB"></div>
    </div>
    <div class="input-hint">支持 HTTP 目录列表、FTP 直连、本地磁盘路径，自动识别</div>

    <div class="actions" style="margin-top:16px">
      <button class="btn btn-primary" id="scanBtn">扫描比对</button>
      <div class="dir-group" id="dirGroup">
        <button class="dir-btn active" data-dir="ab">B → A</button>
        <button class="dir-btn" data-dir="ba">A → B</button>
      </div>
      <label class="toggle-group">
        <input type="checkbox" id="hashToggle">
        哈希校验
      </label>
    </div>

    <div id="statsBar" class="stats hidden"></div>

    <div class="status" id="status">输入两台设备的 HTTP/FTP 链接，点击「扫描比对」开始</div>

    <div id="progressWrap" class="progress">
      <div class="progress-bar"><div class="progress-bar-fill" id="progressFill"></div></div>
      <div class="progress-text" id="progressText">处理中...</div>
    </div>

    <div id="resultSection" class="hidden">
      <div class="summary" id="summary"></div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th style="width:40px"><input type="checkbox" id="selectAll"></th>
              <th style="width:40px">#</th>
              <th style="width:56px">预览</th>
              <th>文件名</th>
              <th style="width:90px">大小</th>
              <th id="hashTh" style="width:280px" class="hidden">SHA256</th>
            </tr>
          </thead>
          <tbody id="fileList"></tbody>
        </table>
      </div>
      <button class="btn btn-danger" id="syncBtn" disabled>同步到设备A（0 个文件）</button>
    </div>

    <div id="emptyState" class="empty-state" style="margin:0">
      <div>输入设备链接后点击「扫描比对」查看结果</div>
    </div>
  </div>
  </section>

  <!-- ═══ Pixiv 收藏查重 ═══ -->
  <section class="tab-panel" id="tab-pixiv">
  <div class="card">
    <div class="card-title">Pixiv 收藏查重</div>
    <div class="input-group">
      <label for="pixivUid">
        Pixiv UID
        <span class="help-toggle" data-target="helpUid">?</span>
      </label>
      <input type="text" id="pixivUid" placeholder="12345678（个人主页地址栏末尾数字）">
      <div id="helpUid" class="help-text hidden">
        <strong>如何获取 Pixiv UID：</strong>
        <ol>
          <li>打开 <a href="https://www.pixiv.net" target="_blank" style="color:#58a6ff">pixiv.net</a> 并登录</li>
          <li>点击右上角头像进入个人主页</li>
          <li>浏览器地址栏 <code>https://www.pixiv.net/users/</code><strong>12345678</strong> 末尾的数字即是 UID</li>
        </ol>
      </div>
    </div>
    <div class="input-group">
      <label for="pixivPhpsessid">
        PHPSESSID
        <span class="help-toggle" data-target="helpPhpsessid">?</span>
      </label>
      <input type="password" id="pixivPhpsessid" placeholder="浏览器 Cookie 中的 PHPSESSID 值（字母数字）">
      <div id="helpPhpsessid" class="help-text hidden">
        <strong>如何获取 PHPSESSID：</strong>
        <ol>
          <li>在浏览器打开 <a href="https://www.pixiv.net" target="_blank" style="color:#58a6ff">pixiv.net</a> 并登录账号</li>
          <li>按 <code>F12</code> 打开开发者工具</li>
          <li>切换到 <code>Application</code> 标签 → 左侧 <code>Cookies</code> → <code>https://www.pixiv.net</code></li>
          <li>找到 <code>PHPSESSID</code> 这一行，复制其值（一串字母数字）</li>
        </ol>
        <div style="margin-top:6px;color:#f85149;font-size:11px">⚠ PHPSESSID 相当于你的登录凭证，不会上传到任何第三方服务器</div>
      </div>
    </div>
    <div class="input-group" style="margin-bottom:0">
      <label for="pixivPath">本地文件夹路径</label>
      <input type="text" id="pixivPath" placeholder="C:\Users\...\Pictures 或 ftp://192.168.1.100:21/">
      <div class="input-badge" id="badge-pixivPath"></div>
    </div>

    <div class="input-group">
      <label for="pixivLimit">扫描数量（0 = 全部）</label>
      <input type="number" id="pixivLimit" min="0" step="1" placeholder="0">
    </div>

    <div class="actions" style="margin-top:16px;margin-bottom:12px">
      <button class="btn btn-primary" id="pixivFetchBtn">拉取收藏</button>
      <button class="btn btn-danger" id="pixivStopBtn" style="display:none" title="网络请求阶段停止最长等待当前请求超时（30s）；本地扫描阶段需等待当前扫描完成后生效">终止</button>
      <span id="pixivStatus" class="pixiv-status">就绪</span>
    </div>

    <div id="pixivResult" class="hidden">
      <div class="pixiv-stats">
        <span>收藏总数: <strong id="pixivTotal">0</strong></span>
        <span>本地图片: <strong id="pixivLocalCount">0</strong></span>
        <span>已在 Pixiv 收藏: <strong id="pixivMatched">0</strong></span>
      </div>
      <div class="table-wrap" style="margin-top:12px">
        <table>
          <thead>
            <tr>
              <th style="width:40px">#</th>
              <th style="width:56px">预览</th>
              <th>文件名</th>
              <th style="width:80px">大小</th>
              <th style="width:100px">Illust ID</th>
              <th style="width:90px">分p</th>
            </tr>
          </thead>
          <tbody id="pixivFileList"></tbody>
        </table>
      </div>
    </div>
  </div>
  </section>

  <!-- ═══ 更多设置 ═══ -->
  <section class="tab-panel" id="tab-settings">
    <div class="card">
      <div class="card-title">界面设置</div>
      <div class="input-group">
        <label for="settingThumbSize">缩略图尺寸</label>
        <input type="range" id="settingThumbSize" min="16" max="128" step="4" style="width:100%">
        <span id="settingThumbSizeVal"></span>px
      </div>
      <div class="input-group">
        <label for="settingPreviewDelay">预览悬浮延迟</label>
        <input type="number" id="settingPreviewDelay" min="100" max="2000" step="50"> ms
      </div>
      <div class="input-group">
        <label for="settingPixivInterval">Pixiv 请求间隔（防限流）</label>
        <input type="number" id="settingPixivInterval" min="0.1" max="10" step="0.1"> s
      </div>
      <div class="input-group">
        <label for="settingMaxRows">结果行数上限</label>
        <input type="number" id="settingMaxRows" min="10" max="5000" step="10">
      </div>
    </div>
    <div class="card">
      <div class="card-title">Pixiv 查重黑名单（illust ID）</div>
      <div class="input-group">
        <input type="text" id="blacklistInput" placeholder="作品 ID 或作品链接，如 https://www.pixiv.net/artworks/123456">
        <div class="input-badge" id="blacklistMsg"></div>
      </div>
      <div class="actions">
        <button class="btn btn-primary" id="blacklistAddBtn">添加</button>
        <button class="btn btn-danger" id="blacklistClearBtn">清空</button>
      </div>
      <div id="blacklistList"></div>
    </div>
  </section>

  <!-- ═══ 日志 ═══ -->
  <section class="tab-panel" id="tab-logs">
    <div class="card">
      <div class="card-title">命令行日志</div>
      <div style="display:flex;gap:8px;align-items:center;margin-bottom:8px">
        <label class="toggle-group"><input type="checkbox" id="logAutoScroll" checked> 自动滚动</label>
        <button class="btn" id="logPauseBtn">暂停</button>
        <button class="btn btn-danger" id="logClearBtn">清空</button>
      </div>
      <div id="logList" style="background:#0d1117;border:1px solid #30363d;border-radius:6px;height:480px;overflow-y:auto;padding:10px 12px;font-family:'SFMono-Regular',Consolas,monospace;font-size:12px;line-height:1.6"></div>
    </div>
  </section>
  </div>

  <!-- ═══ 预览面板（在所有标签页之外，避免 position:fixed 嵌套问题）═══ -->
  <div id="previewPanel" class="preview-panel">
    <img id="previewImg" src="" alt="preview">
    <div class="preview-name" id="previewName"></div>
  </div>
</div>

<script>
// ─── Tab registry ────────────────────────────────────────────────
// 【新增标签三步】1) 在 HTML 加 <section class="tab-panel" id="tab-xxx">
//  2) 在 TABS 数组加 {id:'xxx', title:'名称'}  3) 往该 section 填充内容
const TABS = [
  { id: 'device',  title: '设备同步' },
  { id: 'pixiv',   title: 'Pixiv 查重' },
  { id: 'settings',title: '更多设置' },
  { id: 'logs',    title: '日志' },
];

function activateTab(id) {
  TABS.forEach(t => {
    const panel = document.getElementById('tab-' + t.id);
    if (panel) panel.classList.toggle('active', t.id === id);
  });
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.tab === id);
  });
}

function renderTabBar() {
  const bar = document.getElementById('tabBar');
  bar.innerHTML = TABS.map(t =>
    '<button class="tab-btn" data-tab="' + t.id + '">' + t.title + '</button>'
  ).join('');
  bar.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', function() { activateTab(this.dataset.tab); });
  });
}
renderTabBar();
activateTab('device');

const urlA = document.getElementById('urlA');
const urlB = document.getElementById('urlB');
const scanBtn = document.getElementById('scanBtn');
const hashToggle = document.getElementById('hashToggle');
const statusEl = document.getElementById('status');
const resultSection = document.getElementById('resultSection');
const emptyState = document.getElementById('emptyState');
const summary = document.getElementById('summary');
const fileList = document.getElementById('fileList');
const selectAll = document.getElementById('selectAll');
const syncBtn = document.getElementById('syncBtn');
const hashTh = document.getElementById('hashTh');
const progressWrap = document.getElementById('progressWrap');
const progressFill = document.getElementById('progressFill');
const progressText = document.getElementById('progressText');

let currentFiles = [];
let scanDir = 'ab';  // 'ab' = B→A 正向, 'ba' = A→B 反向
let loadedFilesA = [];
let loadedFilesB = [];

// ─── Config auto-fill & save ───────────────────────────────────
let globalConfig = null;   // 供设置 tab / 预览延迟 / 缩略图尺寸读取

async function loadConfig() {
  try {
    const res = await fetch('/api/config');
    const cfg = await res.json();
    globalConfig = cfg;
    if (cfg.dev1ceA) urlA.value = cfg.dev1ceA;
    if (cfg.dev1ceB) urlB.value = cfg.dev1ceB;
    if (cfg.PixivUID) document.getElementById('pixivUid').value = cfg.PixivUID;
    if (cfg.PHPSESSID) document.getElementById('pixivPhpsessid').value = cfg.PHPSESSID;
    if (cfg.PixivL) document.getElementById('pixivPath').value = cfg.PixivL;
    if (cfg.pixivLimit != null) document.getElementById('pixivLimit').value = cfg.pixivLimit;
    // 缩略图尺寸联动: CSS 变量 --thumb-size
    const ts = parseInt(cfg.thumbnailSize) || 48;
    document.documentElement.style.setProperty('--thumb-size', ts + 'px');
    // 设置 tab 控件填充
    fillSettingsControls();
  } catch (e) {
    // config 文件不存在或解析失败，静默忽略
  }
}

async function saveConfig() {
  const data = {
    dev1ceA: urlA.value.trim(),
    dev1ceB: urlB.value.trim(),
    PixivUID: document.getElementById('pixivUid').value.trim(),
    PHPSESSID: document.getElementById('pixivPhpsessid').value.trim(),
    PixivL: document.getElementById('pixivPath').value.trim(),
    pixivLimit: document.getElementById('pixivLimit').value.trim(),
    thumbnailSize: settingThumbSize.value,
    previewDelay: settingPreviewDelay.value,
    pixivInterval: settingPixivInterval.value,
    maxRows: settingMaxRows.value,
  };
  try {
    await fetch('/api/config/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
  } catch (e) {
    // 保存失败静默忽略
  }
}

// ─── 输入框智能识别（类型徽标 / 协议补全 / 链接提取）─────────────────
// 徽标判定与后端 is_local_path 一致: ^[a-zA-Z]:[\\/] 与 file:/// 判为本地路径

function detectAddressType(val) {
  if (!val) return null;
  if (/^https?:\/\//i.test(val)) return { cls: 'http', text: 'HTTP 链接' };
  if (/^ftp:\/\//i.test(val)) return { cls: 'ftp', text: 'FTP 链接' };
  if (/^file:\/\//i.test(val) || /^[a-zA-Z]:[\\/]/.test(val)) return { cls: 'local', text: '本地路径' };
  return { cls: 'invalid', text: '无法识别的地址格式' };
}

function setBadge(badgeId, info) {
  const b = document.getElementById(badgeId);
  if (!b) return;
  b.className = 'input-badge' + (info ? ' ' + info.cls : '');
  b.textContent = info ? info.text : '';
}

const ADDR_INPUTS = [
  { el: urlA, badge: 'badge-urlA' },
  { el: urlB, badge: 'badge-urlB' },
  { el: document.getElementById('pixivPath'), badge: 'badge-pixivPath' },
];

let badgeTimers = {};
ADDR_INPUTS.forEach(item => {
  const el = item.el;
  if (!el) return;
  el.addEventListener('input', function() {
    clearTimeout(badgeTimers[item.badge]);
    badgeTimers[item.badge] = setTimeout(() => {
      setBadge(item.badge, detectAddressType(el.value.trim()));
    }, 300);
  });
  el.addEventListener('blur', function() {
    const val = el.value.trim();
    // 协议自动补全: 形如 192.168.1.100:1234 的无协议地址 → 补 http://
    if (/^([\w.-]+:\d{1,5})(\/.*)?$/.test(val)) {
      el.value = 'http://' + val;
      setBadge(item.badge, { cls: 'http', text: '已自动补全 http://' });
    } else {
      setBadge(item.badge, detectAddressType(val));
    }
  });
});

// 粘贴 Pixiv 用户页链接 → 提取 UID 填入
function extractPixivUid(str) {
  const m = /pixiv\.net\/users\/(\d+)/i.exec(str || '');
  return m ? m[1] : null;
}
const pixivUidInput = document.getElementById('pixivUid');
function extractUidFromInput() {
  const uid = extractPixivUid(pixivUidInput.value);
  if (uid) pixivUidInput.value = uid;
}
pixivUidInput.addEventListener('blur', extractUidFromInput);
pixivUidInput.addEventListener('paste', function() {
  setTimeout(extractUidFromInput, 50);  // 等粘贴完成后再读值
});

const statsBar = document.getElementById('statsBar');
const dirBtns = document.querySelectorAll('.dir-btn');

// ─── Direction toggle ─────────────────────────────────────────────────

dirBtns.forEach(btn => {
  btn.addEventListener('click', function() {
    if (this.dataset.dir === scanDir) return;
    scanDir = this.dataset.dir;
    dirBtns.forEach(b => b.classList.toggle('active', b.dataset.dir === scanDir));
    if (loadedFilesA.length > 0 && loadedFilesB.length > 0) {
      runDedup();
      const dirLabel = scanDir === 'ab' ? 'B→A' : 'A→B';
      if (currentFiles.length === 0) {
        setStatus('切换方向：' + dirLabel + ' 方向无待同步文件', 'success');
        resultSection.classList.add('hidden');
      } else {
        setStatus('切换方向：' + dirLabel + ' 方向有 ' + currentFiles.length + ' 个文件', 'success');
        renderTable();
        resultSection.classList.remove('hidden');
      }
    }
  });
});

function logToServer(cat, msg) {
  fetch('/api/log?cat=' + encodeURIComponent(cat) + '&msg=' + encodeURIComponent(msg), { method: 'POST' });
}

function setStatus(msg, type) {
  statusEl.innerHTML = msg;
  statusEl.className = 'status' + (type ? ' ' + type : '');
}

function showProgress(show) {
  progressWrap.classList.toggle('active', show);
}

function setProgress(pct, text) {
  progressFill.style.width = pct + '%';
  progressText.textContent = text;
}

async function doScan() {
  const u1 = urlA.value.trim();
  const u2 = urlB.value.trim();
  if (!u1 || !u2) { setStatus('请填写两台设备的链接或路径', 'error'); return; }

  scanBtn.disabled = true;
  setStatus('正在扫描设备 A...', 'loading');
  showProgress(true);
  setProgress(20, '正在扫描设备 A...');
  resultSection.classList.add('hidden');
  statsBar.classList.add('hidden');

  logToServer('SCAN', '开始扫描比对: ' + scanDir);

  try {
    const [res1, res2] = await Promise.all([
      fetch('/api/list?url=' + encodeURIComponent(u1)),
      fetch('/api/list?url=' + encodeURIComponent(u2))
    ]);

    const data1 = await res1.json();
    const data2 = await res2.json();

    if (data1.error) { setStatus('设备 A 连接失败: ' + data1.error, 'error'); scanBtn.disabled = false; showProgress(false); return; }
    if (data2.error) { setStatus('设备 B 连接失败: ' + data2.error, 'error'); scanBtn.disabled = false; showProgress(false); return; }

    loadedFilesA = data1.files || [];
    loadedFilesB = data2.files || [];

    setProgress(50, '正在比对去重...');

    // 显示设备统计
    renderStats(loadedFilesA, loadedFilesB);

    // 去重
    runDedup();

    showProgress(false);

    if (currentFiles.length === 0) {
      if (scanDir === 'ab') {
        setStatus('扫描完成，设备 B 中没有发现新文件', 'success');
      } else {
        setStatus('扫描完成，设备 A 中没有发现新文件', 'success');
      }
      logToServer('DONE', '扫描完成，无新文件');
      scanBtn.disabled = false;
      return;
    }

    const dirLabel = scanDir === 'ab' ? 'B→A' : 'A→B';
    setStatus('扫描完成，' + dirLabel + ' 方向有 ' + currentFiles.length + ' 个文件待同步', 'success');
    logToServer('DONE', '发现 ' + currentFiles.length + ' 个待同步文件');
    renderTable();
    resultSection.classList.remove('hidden');

    if (hashToggle.checked) {
      await doHash();
    }
  } catch (e) {
    setStatus('扫描出错: ' + e.message, 'error');
  }
  scanBtn.disabled = false;
}

function renderStats(filesA, filesB) {
  const countA = filesA.length;
  const countB = filesB.length;
  const sizeA = filesA.reduce((s, f) => s + (f.size || 0), 0);
  const sizeB = filesB.reduce((s, f) => s + (f.size || 0), 0);

  statsBar.innerHTML =
    '<div class="stat-item"><div class="stat-label">设备 A</div>' +
    '<div class="stat-value">' + countA + '</div>' +
    '<div class="stat-sub">' + formatSize(sizeA) + '</div></div>' +
    '<div class="stat-item"><div class="stat-label">设备 B</div>' +
    '<div class="stat-value">' + countB + '</div>' +
    '<div class="stat-sub">' + formatSize(sizeB) + '</div></div>';

  statsBar.classList.remove('hidden');
}

function runDedup() {
  const namesA = new Set(loadedFilesA.map(f => f.name));
  const namesB = new Set(loadedFilesB.map(f => f.name));

  if (scanDir === 'ab') {
    // 正向：B 有 A 没有的
    const unique = loadedFilesB.filter(f => !namesA.has(f.name));
    currentFiles = unique.map((f, i) => ({ ...f, idx: i, hash: null, selected: true }));
  } else {
    // 反向：A 有 B 没有的
    const unique = loadedFilesA.filter(f => !namesB.has(f.name));
    currentFiles = unique.map((f, i) => ({ ...f, idx: i, hash: null, selected: true }));
  }
}

function renderTable() {
  let html = '';
  const srcUrl = scanDir === 'ab' ? urlB.value.trim() : urlA.value.trim();
  currentFiles.forEach((f, i) => {
    const sizeStr = f.size != null ? formatSize(f.size) : '-';
    const delay = Math.min(i * 30, 300);
    const thumbUrl = srcUrl ? '/api/image?url=' + encodeURIComponent(srcUrl) + '&file=' + encodeURIComponent(f.name) : '';
    html += '<tr class="row-enter" style="animation-delay:' + delay + 'ms">';
    html += '<td><input type="checkbox" class="file-cb" data-idx="' + i + '" checked></td>';
    html += '<td>' + (i + 1) + '</td>';
    html += '<td class="thumb-wrap">';
    html += '<img class="thumb" data-src="' + escapeHtml(thumbUrl) + '" src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7" alt="" loading="lazy">';
    html += '</td>';
    html += '<td class="filename"><span class="filename-link" data-idx="' + i + '">' + escapeHtml(f.name) + '</span></td>';
    html += '<td>' + sizeStr + '</td>';
    html += '<td class="file-hash' + (hashToggle.checked ? '' : ' hidden') + '">' + (f.hash || '-') + '</td>';
    html += '</tr>';
  });
  fileList.innerHTML = html;

  hashTh.classList.toggle('hidden', !hashToggle.checked);
  updateSyncBtn();
  loadThumbnails();
  bindPreviewHover();

  document.querySelectorAll('.file-cb').forEach(cb => {
    cb.addEventListener('change', function() {
      const idx = parseInt(this.dataset.idx);
      if (currentFiles[idx]) currentFiles[idx].selected = this.checked;
      updateSyncBtn();
    });
  });
}

// ─── 缩略图懒加载（IntersectionObserver 按需赋值 src）────────────────
// 保留原生 loading="lazy" 兜底; data-src 直接存真实 URL; 已加载后移除 data-src 防重复加载

const thumbObserver = new IntersectionObserver((entries, obs) => {
  entries.forEach(entry => {
    if (!entry.isIntersecting) return;
    const img = entry.target;
    if (img.dataset.src) {
      img.src = img.dataset.src;
      img.removeAttribute('data-src');
    }
    obs.unobserve(img);
  });
}, { rootMargin: '200px' });

function loadThumbnails() {
  // 观察当前所有未加载的 .thumb（设备表与 Pixiv 结果表共用同一机制）
  document.querySelectorAll('.thumb').forEach(img => {
    if (!img.dataset.src) return;
    thumbObserver.observe(img);
  });
}

function observeThumbs(containerEl) {
  // 供 Pixiv 结果表等动态渲染后调用: 仅观察容器内未加载的缩略图
  if (!containerEl) return;
  containerEl.querySelectorAll('.thumb').forEach(img => {
    if (!img.dataset.src) return;
    thumbObserver.observe(img);
  });
}

// ─── Preview hover ─────────────────────────────────────────────────────

let previewTimer = null;
const previewPanel = document.getElementById('previewPanel');
const previewImg = document.getElementById('previewImg');
const previewName = document.getElementById('previewName');

function bindPreviewHover() {
  document.querySelectorAll('.filename-link').forEach(link => {
    link.addEventListener('mouseenter', function(e) {
      const idx = parseInt(this.dataset.idx);
      const f = currentFiles[idx];
      if (!f) return;
      const srcUrl = scanDir === 'ab' ? urlB.value.trim() : urlA.value.trim();
      if (!srcUrl) return;

      // 预览延迟可配置 (config previewDelay, 默认 500ms); null 保护防 loadConfig 未完成
      const delay = parseInt((globalConfig || {}).previewDelay) || 500;
      previewTimer = setTimeout(() => {
        const rect = this.getBoundingClientRect();
        previewImg.src = '/api/image?url=' + encodeURIComponent(srcUrl) + '&file=' + encodeURIComponent(f.name);
        previewName.textContent = f.name + (f.size != null ? ' (' + formatSize(f.size) + ')' : '');
        previewPanel.classList.add('active');

        // Position: below the link, or above if near bottom
        let top = rect.bottom + 8;
        if (top + 520 > window.innerHeight) {
          top = rect.top - 8 - 520;
        }
        let left = Math.min(rect.left, window.innerWidth - 420);
        previewPanel.style.top = Math.max(8, top) + 'px';
        previewPanel.style.left = Math.max(8, left) + 'px';
      }, delay);
    });

    link.addEventListener('mouseleave', function() {
      clearTimeout(previewTimer);
      previewPanel.classList.remove('active');
    });
  });
}

function updateSyncBtn() {
  const count = currentFiles.filter(f => f.selected !== false).length;
  const dirLabel = scanDir === 'ab' ? 'B→A' : 'A→B';
  syncBtn.textContent = '同步到设备' + (scanDir === 'ab' ? 'A' : 'B') + '（' + count + ' 个文件，' + dirLabel + '）';
  syncBtn.disabled = count === 0;
}

async function doHash() {
  const srcUrl = scanDir === 'ab' ? urlB.value.trim() : urlA.value.trim();
  if (!srcUrl) return;

  setProgress(0, '正在计算哈希值...');
  showProgress(true);
  hashTh.classList.remove('hidden');
  logToServer('HASH', '开始哈希校验 ' + currentFiles.length + ' 个文件');

  for (let i = 0; i < currentFiles.length; i++) {
    const f = currentFiles[i];
    setProgress(Math.round((i / currentFiles.length) * 100), '计算哈希值 ' + (i+1) + '/' + currentFiles.length + ': ' + f.name);
    try {
      const res = await fetch('/api/hash?url=' + encodeURIComponent(srcUrl) + '&file=' + encodeURIComponent(f.name), { method: 'POST' });
      const data = await res.json();
      if (data.sha256) {
        f.hash = data.sha256.substring(0, 16) + '...';
        const row = fileList.querySelector('tr:nth-child(' + (i + 1) + ')');
        if (row) {
          const cell = row.querySelector('.file-hash');
          if (cell) { cell.textContent = f.hash; cell.classList.remove('hidden'); }
        }
      }
    } catch (e) {
      // skip
    }
  }
  showProgress(false);
}

async function doSync() {
  const u1 = urlA.value.trim();
  const u2 = urlB.value.trim();
  if (!u1 || !u2) { setStatus('请填写设备链接', 'error'); return; }

  const toSync = currentFiles.filter(f => f.selected !== false);
  if (toSync.length === 0) return;

  // 根据方向决定来源和目标
  const srcUrl = scanDir === 'ab' ? u2 : u1;
  const dstUrl = scanDir === 'ab' ? u1 : u2;
  const dirLabel = scanDir === 'ab' ? 'B→A' : 'A→B';

  syncBtn.disabled = true;
  scanBtn.disabled = true;
  showProgress(true);
  logToServer('SYNC', '开始同步 ' + toSync.length + ' 个文件 (' + dirLabel + ')');

  let success = 0, fail = 0;

  for (let i = 0; i < toSync.length; i++) {
    const f = toSync[i];
    setProgress(Math.round((i / toSync.length) * 100), '正在同步 ' + (i+1) + '/' + toSync.length + ': ' + f.name);
    setStatus('正在复制 ' + f.name + '...（' + (i+1) + '/' + toSync.length + '）', 'loading');

    try {
      const res = await fetch('/api/copy?from=' + encodeURIComponent(srcUrl) + '&to=' + encodeURIComponent(dstUrl) + '&file=' + encodeURIComponent(f.name), { method: 'POST' });
      const data = await res.json();
      if (data.success) { success++; }
      else { fail++; }
    } catch (e) {
      fail++;
    }
  }

  showProgress(false);

  // dirLabel 已在上面定义，直接使用

  if (fail === 0) {
    setStatus('同步完成，成功复制 ' + success + ' 个文件（' + dirLabel + '）', 'success');
    logToServer('DONE', '同步完成: ' + success + '/' + toSync.length + ' 成功');
  } else {
    setStatus('同步完成：成功 ' + success + ' 个，失败 ' + fail + ' 个（' + dirLabel + '）', 'error');
    logToServer('ERROR', '同步完成: ' + success + ' 成功, ' + fail + ' 失败');
  }

  syncBtn.disabled = false;
  scanBtn.disabled = false;
}

function formatSize(bytes) {
  if (bytes == null) return '-';
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / 1024 / 1024).toFixed(1) + ' MB';
}

function escapeHtml(str) {
  const d = document.createElement('div');
  d.textContent = str;
  return d.innerHTML;
}

// ─── Help toggle ──────────────────────────────────────────────────────

document.querySelectorAll('.help-toggle').forEach(el => {
  el.addEventListener('click', function() {
    const target = document.getElementById(this.dataset.target);
    if (target) target.classList.toggle('hidden');
  });
});

// ─── Pixiv bookmark check ─────────────────────────────────────────────

function setPixivStatus(msg, type) {
  const el = document.getElementById('pixivStatus');
  el.textContent = msg;
  el.className = 'pixiv-status' + (type ? ' ' + type : '');
}

let pixivPollTimer = null;

async function doFetchBookmarks() {
  const uid = document.getElementById('pixivUid').value.trim();
  const phpsessid = document.getElementById('pixivPhpsessid').value.trim();
  const path = document.getElementById('pixivPath').value.trim();
  const limitRaw = document.getElementById('pixivLimit').value.trim();

  if (!uid || !phpsessid) { setPixivStatus('请填写 Pixiv UID 和 PHPSESSID', 'error'); return; }
  if (!path) { setPixivStatus('请填写本地文件夹路径', 'error'); return; }

  let limit = 0;
  if (limitRaw !== '') {
    limit = parseInt(limitRaw, 10);
    if (isNaN(limit) || limit < 0) limit = 0;
  }

  const fetchBtn = document.getElementById('pixivFetchBtn');
  const stopBtn = document.getElementById('pixivStopBtn');
  fetchBtn.disabled = true;
  stopBtn.style.display = 'inline-flex';
  setPixivStatus('正在启动 Pixiv 扫描...', 'loading');
  document.getElementById('pixivResult').classList.add('hidden');

  try {
    const res = await fetch('/api/pixiv/bookmarks', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ uid, phpsessid, path, limit })
    });
    const data = await res.json();

    if (data.error) {
      setPixivStatus('错误: ' + data.error, 'error');
      fetchBtn.disabled = false;
      stopBtn.style.display = 'none';
      return;
    }

    // 启动成功 → 1s 轮询 job 状态
    pixivPollTimer = setInterval(pollPixivJob, 1000);
    pollPixivJob();
  } catch (e) {
    setPixivStatus('请求失败: ' + e.message, 'error');
    fetchBtn.disabled = false;
    stopBtn.style.display = 'none';
  }
}

async function pollPixivJob() {
  const fetchBtn = document.getElementById('pixivFetchBtn');
  const stopBtn = document.getElementById('pixivStopBtn');
  try {
    const res = await fetch('/api/pixiv/job');
    const job = await res.json();

    if (job.status === 'fetching') {
      const p = job.progress || {};
      setPixivStatus('拉取中 ' + (p.fetched || 0) + '/' + (p.total || 0), 'loading');
      return;
    }
    if (job.status === 'scanning') {
      setPixivStatus('扫描本地目录…', 'loading');
      return;
    }
    if (job.status === 'matching') {
      const p = job.progress || {};
      setPixivStatus('匹配中，已命中 ' + (p.fetched || 0) + ' 个', 'loading');
      return;
    }

    // 终态: 停止轮询, 恢复按钮
    clearInterval(pixivPollTimer);
    pixivPollTimer = null;
    fetchBtn.disabled = false;
    stopBtn.style.display = 'none';

    if (job.status === 'done') {
      const r2 = await fetch('/api/pixiv/job/result');
      const resultData = await r2.json();
      renderPixivResult(job.summary, resultData.matched || []);
    } else if (job.status === 'stopped') {
      setPixivStatus('已终止', 'error');
    } else if (job.status === 'error') {
      setPixivStatus('错误: ' + (job.error || '未知错误'), 'error');
    }
  } catch (e) {
    // 轮询失败静默, 下个周期重试
  }
}

function renderPixivResult(summary, matched) {
  document.getElementById('pixivTotal').textContent = summary ? (summary.total_bookmarks ?? 0) : 0;
  document.getElementById('pixivLocalCount').textContent = summary ? (summary.local_count ?? 0) : 0;
  document.getElementById('pixivMatched').textContent = summary ? (summary.matched_count ?? 0) : 0;

  const tbody = document.getElementById('pixivFileList');
  const pixivPath = document.getElementById('pixivPath').value.trim();
  if (matched.length > 0) {
    let html = '';
    matched.forEach((f, i) => {
      const sizeStr = f.size != null ? formatSize(f.size) : '-';
      const thumbUrl = pixivPath ? '/api/image?url=' + encodeURIComponent(pixivPath) + '&file=' + encodeURIComponent(f.name) : '';
      const pageStr = (f.page != null && f.pageCount != null) ? ('p' + f.page + '/共' + f.pageCount + 'p') : '-';
      html += '<tr>';
      html += '<td>' + (i + 1) + '</td>';
      html += '<td class="thumb-wrap">';
      html += '<img class="thumb" data-src="' + escapeHtml(thumbUrl) + '" src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7" alt="" loading="lazy">';
      html += '</td>';
      html += '<td class="filename">' + escapeHtml(f.name) + '</td>';
      html += '<td>' + sizeStr + '</td>';
      html += '<td>' + escapeHtml(f.illust_id || '') + '</td>';
      html += '<td>' + pageStr + '</td>';
      html += '</tr>';
    });
    tbody.innerHTML = html;
    observeThumbs(tbody);   // 复用 todo 11 懒加载机制
  } else {
    tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:#484f58;padding:20px">没有找到匹配的文件</td></tr>';
  }
  document.getElementById('pixivResult').classList.remove('hidden');
  if (matched.length > 0) {
    setPixivStatus('查重完成，发现 ' + matched.length + ' 个已在 Pixiv 收藏的文件', 'success');
  } else {
    setPixivStatus('查重完成，本地文件均不在 Pixiv 收藏中', 'success');
  }
}

function stopPixivJob() {
  fetch('/api/pixiv/bookmarks/stop', { method: 'POST' }).catch(() => {});
  setPixivStatus('正在终止…', 'loading');
}

document.getElementById('pixivFetchBtn').addEventListener('click', doFetchBookmarks);
document.getElementById('pixivStopBtn').addEventListener('click', stopPixivJob);

scanBtn.addEventListener('click', doScan);
hashToggle.addEventListener('change', function() {
  if (currentFiles.length > 0) {
    if (this.checked) {
      document.querySelectorAll('.file-hash').forEach(el => el.classList.remove('hidden'));
      doHash();
    } else {
      hashTh.classList.add('hidden');
      document.querySelectorAll('.file-hash').forEach(el => el.classList.add('hidden'));
    }
  }
});
selectAll.addEventListener('change', function() {
  currentFiles.forEach(f => f.selected = this.checked);
  document.querySelectorAll('.file-cb').forEach(cb => cb.checked = this.checked);
  updateSyncBtn();
});
syncBtn.addEventListener('click', doSync);

// ─── 日志面板（轮询 /api/logs; 六色映射; 自动滚动/暂停/清空）─────────
let logLastId = 0;
let logPaused = false;
const CATS = ['SCAN', 'HASH', 'SYNC', 'IMAGE', 'DONE', 'ERROR'];

async function pollLogs() {
  if (logPaused) return;
  try {
    const resp = await fetch('/api/logs?since=' + logLastId);
    const data = await resp.json();
    const list = document.getElementById('logList');
    if (data.truncated) {
      // 缓冲被清空/挤出/重启: 清空列表, 下次轮询从 0 全量重载
      list.innerHTML = '';
      logLastId = 0;
      return;
    }
    data.logs.forEach(log => {
      // cat 白名单化（防 class 属性注入 XSS）; msg 必须 escapeHtml 后插入
      const cls = CATS.includes(log.cat) ? log.cat : 'INFO';
      const line = document.createElement('div');
      line.className = 'log-line';
      line.innerHTML = '<span class="cat-' + cls + '">[' + escapeHtml(log.ts) + '] [' +
        escapeHtml(log.cat) + '] ' + escapeHtml(log.msg) + '</span>';
      list.appendChild(line);
    });
    if (data.logs.length > 0) {
      logLastId = data.next_id;
      if (document.getElementById('logAutoScroll').checked) {
        list.scrollTop = list.scrollHeight;
      }
    }
  } catch (e) {
    // 轮询失败静默, 下个周期重试
  }
}
setInterval(pollLogs, 1000);

document.getElementById('logPauseBtn').addEventListener('click', function() {
  logPaused = !logPaused;
  this.textContent = logPaused ? '继续' : '暂停';
});
document.getElementById('logClearBtn').addEventListener('click', async function() {
  try {
    await fetch('/api/logs/clear', { method: 'POST' });
  } catch (e) { /* 忽略 */ }
  document.getElementById('logList').innerHTML = '';
  logLastId = 0;
});

// ─── 更多设置 tab（控件持久化 + 黑名单管理）───────────────────────
const settingThumbSize = document.getElementById('settingThumbSize');
const settingThumbSizeVal = document.getElementById('settingThumbSizeVal');
const settingPreviewDelay = document.getElementById('settingPreviewDelay');
const settingPixivInterval = document.getElementById('settingPixivInterval');
const settingMaxRows = document.getElementById('settingMaxRows');

function fillSettingsControls() {
  const cfg = globalConfig || {};
  settingThumbSize.value = cfg.thumbnailSize != null ? cfg.thumbnailSize : 48;
  settingThumbSizeVal.textContent = settingThumbSize.value;
  settingPreviewDelay.value = cfg.previewDelay != null ? cfg.previewDelay : 500;
  settingPixivInterval.value = cfg.pixivInterval != null ? cfg.pixivInterval : 0.8;
  settingMaxRows.value = cfg.maxRows != null ? cfg.maxRows : 1000;
}

// 缩略图滑块: 实时写 --thumb-size, blur/change 时保存
settingThumbSize.addEventListener('input', function() {
  const v = this.value;
  settingThumbSizeVal.textContent = v;
  document.documentElement.style.setProperty('--thumb-size', v + 'px');
});
[settingThumbSize, settingPreviewDelay, settingPixivInterval, settingMaxRows].forEach(el => {
  el.addEventListener('blur', saveConfig);
  el.addEventListener('change', saveConfig);
});

// 黑名单管理
const blacklistList = document.getElementById('blacklistList');

function setBlacklistMsg(text, type) {
  const m = document.getElementById('blacklistMsg');
  m.className = 'input-badge' + (type ? ' ' + type : '');
  m.textContent = text || '';
}

async function loadBlacklistUI() {
  try {
    const res = await fetch('/api/blacklist');
    const data = await res.json();
    const ids = data.ids || [];
    if (ids.length === 0) {
      blacklistList.innerHTML = '<div style="color:#484f58;font-size:13px;padding:8px 0">黑名单为空</div>';
      return;
    }
    blacklistList.innerHTML = ids.map(id =>
      '<div style="display:flex;align-items:center;justify-content:space-between;padding:6px 8px;border-bottom:1px solid #21262d;font-family:monospace;font-size:13px">' +
      '<span>' + escapeHtml(id) + '</span>' +
      '<button class="btn btn-danger" style="padding:4px 12px;font-size:12px" data-remove="' + escapeHtml(id) + '">删除</button>' +
      '</div>'
    ).join('');
    blacklistList.querySelectorAll('[data-remove]').forEach(btn => {
      btn.addEventListener('click', async function() {
        try {
          await fetch('/api/blacklist/remove', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id: this.dataset.remove })
          });
        } catch (e) { /* 忽略 */ }
        loadBlacklistUI();
      });
    });
  } catch (e) { /* 忽略 */ }
}

document.getElementById('blacklistAddBtn').addEventListener('click', async function() {
  const input = document.getElementById('blacklistInput');
  const raw = input.value.trim();
  if (!raw) { setBlacklistMsg('请输入作品 ID 或链接'); return; }
  try {
    const res = await fetch('/api/blacklist/add', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: raw })
    });
    const data = await res.json();
    if (data.error) {
      setBlacklistMsg('添加失败: ' + data.error, 'error');
      return;
    }
    input.value = '';
    setBlacklistMsg('已添加', 'success');
    loadBlacklistUI();
  } catch (e) { /* 忽略 */ }
});

document.getElementById('blacklistClearBtn').addEventListener('click', async function() {
  try {
    await fetch('/api/blacklist/clear', { method: 'POST' });
  } catch (e) { /* 忽略 */ }
  setBlacklistMsg('已清空', 'success');
  loadBlacklistUI();
});

// ─── Config blur save ──────────────────────────────────────────
urlA.addEventListener('blur', saveConfig);
urlB.addEventListener('blur', saveConfig);
document.getElementById('pixivUid').addEventListener('blur', saveConfig);
document.getElementById('pixivPhpsessid').addEventListener('blur', saveConfig);
document.getElementById('pixivPath').addEventListener('blur', saveConfig);
document.getElementById('pixivLimit').addEventListener('blur', saveConfig);

// 加载配置文件
loadConfig();
loadBlacklistUI();
</script>
</body>
</html>"""

# ─── URL helpers ─────────────────────────────────────────────────────────────

def is_ftp(url):
    return url.lower().startswith('ftp://')

def resolve_url(base, filename):
    base = base.rstrip('/') + '/'
    return base + urllib.parse.quote(filename)

def parse_ftp_info(url):
    parsed = urllib.parse.urlparse(url)
    return {
        'host': parsed.hostname or 'localhost',
        'port': parsed.port or 21,
        'user': parsed.username or 'anonymous',
        'password': parsed.password or 'anonymous@',
        'path': parsed.path or '/'
    }

# ─── HTTP helpers ────────────────────────────────────────────────────────────

def http_fetch(url, timeout=15):
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode('utf-8', errors='replace')
        return body, resp.status

def http_download(url, timeout=30):
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()

def http_put(url, data, timeout=60):
    req = urllib.request.Request(url, data=data, method='PUT')
    req.add_header('Content-Type', 'application/octet-stream')
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status

# ─── FTP helpers ─────────────────────────────────────────────────────────────

def ftp_list(url):
    info = parse_ftp_info(url)
    ftp = ftplib.FTP()
    ftp.connect(info['host'], info['port'], timeout=15)
    ftp.login(info['user'], info['password'])
    result = []
    try:
        ftp.cwd(info['path'])
        try:
            for entry in ftp.mlsd():
                name, attrs = entry
                if attrs.get('type') == 'file':
                    size = int(attrs.get('size', 0))
                    result.append({'name': name, 'size': size})
                elif attrs.get('type') == 'dir':
                    pass
        except (ftplib.error_perm, AttributeError):
            try:
                names = ftp.nlst()
                for name in names:
                    if name not in ('.', '..'):
                        result.append({'name': name, 'size': 0})
            except ftplib.error_perm:
                lines = []
                ftp.dir(lines.append)
                for line in lines:
                    parts = line.split()
                    if len(parts) >= 9 and not parts[-1].startswith('.'):
                        result.append({'name': parts[-1], 'size': 0})
    finally:
        try:
            ftp.quit()
        except:
            pass
    return result

def ftp_download(url, filename):
    info = parse_ftp_info(url)
    ftp = ftplib.FTP()
    ftp.connect(info['host'], info['port'], timeout=30)
    ftp.login(info['user'], info['password'])
    try:
        ftp.cwd(info['path'])
        buf = io.BytesIO()
        ftp.retrbinary('RETR ' + filename, buf.write)
        return buf.getvalue()
    finally:
        try:
            ftp.quit()
        except:
            pass

def ftp_upload(url, filename, data):
    info = parse_ftp_info(url)
    ftp = ftplib.FTP()
    ftp.connect(info['host'], info['port'], timeout=60)
    ftp.login(info['user'], info['password'])
    try:
        ftp.cwd(info['path'])
        ftp.storbinary('STOR ' + filename, io.BytesIO(data))
    finally:
        try:
            ftp.quit()
        except:
            pass

# ─── Directory listing parser (HTTP HTML) ────────────────────────────────────

def parse_html_listing(html):
    files = []
    pattern = re.compile(r'<a\s+href="([^"]*)"[^>]*>([^<]*)</a>', re.IGNORECASE)
    for match in pattern.finditer(html):
        href = match.group(1).strip()
        text = match.group(2).strip()
        if href in ('../', './') or href.endswith('/') or href.startswith('?'):
            continue
        name = text or href
        ext = os.path.splitext(name)[1].lower()
        if ext in IMAGE_EXTS:
            files.append({'name': name, 'size': 0})
    return files

# ─── Local directory scanner ─────────────────────────────────────────────────

def is_local_path(path):
    """检测是否为本地磁盘路径"""
    if path.lower().startswith('file:///'):
        return True
    if re.match(r'^[a-zA-Z]:[\\/]', path):
        return True
    if re.match(r'^[a-zA-Z]:\\', path):
        return True
    return False

def strip_file_prefix(path):
    """去掉 file:/// 前缀"""
    if path.lower().startswith('file:///'):
        return path[8:]  # file:///C:/ → C:/
    if path.lower().startswith('file://'):
        return path[7:]
    return path

def local_list(path):
    """扫描本地目录，返回文件列表"""
    path = strip_file_prefix(path)
    files = []
    try:
        for root, dirs, filenames in os.walk(path):
            for name in filenames:
                ext = os.path.splitext(name)[1].lower()
                if ext in IMAGE_EXTS:
                    full = os.path.join(root, name)
                    try:
                        size = os.path.getsize(full)
                    except:
                        size = 0
                    # 相对于扫描目录的路径
                    rel = os.path.relpath(full, path)
                    files.append({'name': rel, 'size': size})
    except Exception as e:
        console_log('ERROR', f'本地扫描失败: {path} - {e}')
        raise
    return files

# ─── HTTP Request Handler ────────────────────────────────────────────────────

def _read_remote_file(url, filename):
    """通用远程文件读取，支持 HTTP、FTP、本地路径"""
    if is_local_path(url):
        base = strip_file_prefix(url)
        full = os.path.join(base, filename)
        with open(full, 'rb') as f:
            return f.read()
    elif is_ftp(url):
        return ftp_download(url, filename)
    else:
        file_url = resolve_url(url, filename)
        return http_download(file_url)

# ─── Pixiv API ────────────────────────────────────────────────────────────
#
# 接口文档（供后期维护参考）
#
# [POST] /api/pixiv/bookmarks
#   描述: 拉取 Pixiv 用户收藏，与本地文件比对查重
#   请求头: Content-Type: application/json
#   请求体: {
#     "uid":       string  — Pixiv 用户 ID（必填）
#     "phpsessid": string  — 浏览器 Cookie 中的 PHPSESSID（必填）
#     "path":      string  — 本地文件夹路径或 FTP/HTTP 链接（必填）
#   }
#   成功响应: {
#     "total_bookmarks": int     — 收藏总数
#     "local_count":     int     — 本地扫描文件数
#     "matched_count":   int     — 匹配命中数
#     "matched":         array   — [{name, size, illust_id}, ...]
#   }
#   错误响应: { "error": string }
#   注意事项:
#     - PHPSESSID 有有效期，过期需重新从浏览器复制
#     - 自动拉取公开 + 非公开收藏，间隔 0.8s 防限流
#     - 依赖 Pixiv Web API (ajax), 非官方 OAuth
#     - 本地文件名通过正则 ^(\d+)_p\d+ 提取 illust_id
#
# [POST] /api/pixiv/bookmarks  (前端 ⇒ 服务器)
#   JS: fetch('/api/pixiv/bookmarks', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({uid, phpsessid, path}) })
#
# 如需新增 Pixiv 功能（如拉取指定画师作品、关键词搜索），
# 可在此文件新增函数并在 SyncHandler 中注册新路由:
#   def _handle_pixiv_xxx(self):    # handler
#   elif parsed.path == '/api/pixiv/xxx': self._handle_pixiv_xxx()   # do_POST / do_GET

PIXIV_BOOKMARK_URL = 'https://www.pixiv.net/ajax/user/{uid}/illusts/bookmarks'
PIXIV_REFERER = 'https://www.pixiv.net/'
PIXIV_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'

# ─── Pixiv 查重黑名单 (blacklist.csv) ────────────────────────────────────────
# 格式: 表头 "illust_id" + 每行一个作品 ID。表头行预留扩展列（如 tag/user_id）空间。
BLACKLIST_PATH = os.path.join(runtime_dir(), 'blacklist.csv')
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
    """原子写: 临时文件 + os.replace, 避免并发读看到半写文件"""
    with BLACKLIST_LOCK:
        tmp = BLACKLIST_PATH + '.tmp'
        try:
            with open(tmp, 'w', encoding='utf-8') as f:
                f.write('illust_id\n')
                for i in sorted(ids):
                    f.write(i + '\n')
            os.replace(tmp, BLACKLIST_PATH)
        except OSError:
            try:
                os.remove(tmp)
            except OSError:
                pass


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

            for wid, page_count in batch.items():
                if wid not in bookmarks:
                    bookmarks[wid] = page_count

            request_count += 1
            skip_note = f' 黑名单跳过{skipped_total}' if skipped_total else ''
            console_log('SCAN', f'Pixiv({visibility}): {len(bookmarks)}/{stream_total} 请求{request_count}次{skip_note}')
            update_progress()

            # limit 预算: 非黑名单累计数达标即停
            if limit and limit > 0 and len(bookmarks) >= limit:
                return bookmarks

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
    'summary': None,             # done 时: {total_bookmarks, local_count, matched_count}
    'error': None,
    'result': None,              # done 时: matched 数组
}


def _scan_local_files(path):
    """扫描本地目录/FTP/HTTP 源, 返回 [{name, size}]（保持原 _handle_pixiv_bookmarks 的扫描方式）"""
    if is_local_path(path):
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
        bookmarks = fetch_fn(uid, phpsessid, limit, pixiv_job['stop'], blacklist, interval)
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

        # ── matching（分p级: 按 pageCount 存在性匹配）──
        if pixiv_job['stop'].is_set():
            set_state(status='stopped')
            return
        set_state(status='matching', progress={'phase': 'matching', 'fetched': 0, 'total': len(local_files)})
        matched = []
        for f in local_files:
            if pixiv_job['stop'].is_set():
                set_state(status='stopped')
                return
            illust_id, page = extract_illust_page(f['name'])
            if illust_id and is_page_covered(illust_id, page, bookmarks):
                matched.append({
                    'name': f['name'],
                    'size': f.get('size', 0),
                    'illust_id': illust_id,
                    'page': page,
                    'pageCount': bookmarks[illust_id],
                })
            set_state(progress={'phase': 'matching', 'fetched': len(matched), 'total': len(local_files)})

        matched = matched[:max_rows]
        set_state(status='done',
                  progress={'phase': 'done', 'fetched': len(matched), 'total': len(matched)},
                  summary={'total_bookmarks': len(bookmarks),
                           'local_count': len(local_files),
                           'matched_count': len(matched)},
                  result=matched)
    except urllib.error.HTTPError as e:
        if e.code == 403:
            msg = 'Pixiv 认证失败，请检查 PHPSESSID 是否有效或已过期'
        elif e.code == 404:
            msg = 'Pixiv 用户不存在，请检查 UID'
        else:
            msg = f'HTTP {e.code}'
        console_log('ERROR', f'Pixiv 查重失败: {msg}')
        set_state(status='error', error=msg)
    except Exception as e:
        console_log('ERROR', f'Pixiv 查重失败: {e}')
        set_state(status='error', error=str(e))


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


class SyncHandler(http.server.BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        pass  # suppress default logging

    def _send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(HTML.encode('utf-8'))

    def _send_error(self, code=404, msg='Not Found'):
        self.send_response(code)
        self.send_header('Content-Type', 'text/plain; charset=utf-8')
        self.end_headers()
        self.wfile.write(msg.encode('utf-8'))

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', '*')
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

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
                files = local_list(phone_url)
                console_log('SCAN', f'本地扫描: {len(files)} 个文件 ({phone_url})')
            elif is_ftp(phone_url):
                entries = ftp_list(phone_url)
                files = [e for e in entries
                         if os.path.splitext(e['name'])[1].lower() in IMAGE_EXTS]
            else:
                body, status = http_fetch(phone_url)
                if status >= 400:
                    console_log('ERROR', f'列表请求失败 HTTP {status}: {phone_url}')
                    self._send_json({'error': 'HTTP ' + str(status), 'files': []})
                    return
                files = parse_html_listing(body)

            console_log('SCAN', f'成功: {len(files)} 个文件')
            self._send_json({'files': files, 'total': len(files)})
        except Exception as e:
            console_log('ERROR', f'列表请求失败: {phone_url} - {e}')
            self._send_json({'error': str(e), 'files': []})

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
            self._send_json({'error': str(e)})

    def _handle_copy(self, params):
        from_url = params.get('from', [None])[0]
        to_url = params.get('to', [None])[0]
        filename = params.get('file', [None])[0]

        if not from_url or not to_url or not filename:
            self._send_json({'success': False, 'error': 'Missing parameters'})
            return

        try:
            data = _read_remote_file(from_url, filename)

            if is_local_path(to_url):
                base = strip_file_prefix(to_url)
                dst = os.path.join(base, filename)
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
            self._send_json({'success': False, 'filename': filename, 'error': str(e)})

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
            self._send_json({'error': f'Invalid request body: {e}'})
            return

        uid = str(req_data.get('uid', '')).strip()
        phpsessid = str(req_data.get('phpsessid', '')).strip()
        local_path = str(req_data.get('path', '')).strip()

        if not uid or not phpsessid:
            self._send_json({'error': '请填写 Pixiv UID 和 PHPSESSID'})
            return
        if not local_path:
            self._send_json({'error': '请填写本地文件夹路径'})
            return

        try:
            limit = int(req_data.get('limit', load_config().get('pixivLimit', 0)))
        except (TypeError, ValueError):
            limit = load_config().get('pixivLimit', 0)

        ok, msg = _start_pixiv_job(uid, phpsessid, local_path, limit)
        if not ok:
            self._send_json({'error': msg})
            return
        console_log('SCAN', f'Pixiv: 开始拉取收藏 (UID={uid}, limit={limit})')
        self._send_json({'ok': True, 'status': 'fetching'})

    def _handle_pixiv_stop(self):
        """POST /api/pixiv/bookmarks/stop: 置 stop 事件, Job 在下个检查点停止"""
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
            self._send_json({'error': f'Invalid request body: {e}'})
            return
        nid = normalize_illust_id(req_data.get('id', ''))
        if not nid:
            self._send_json({'error': '无法识别的作品 ID'})
            return
        ids = load_blacklist()
        ids.add(nid)
        save_blacklist(ids)
        console_log('SCAN', f'Pixiv: 黑名单添加 {nid} (共 {len(ids)} 个)')
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
            self._send_json({'error': f'Invalid request body: {e}'})
            return
        nid = normalize_illust_id(req_data.get('id', ''))
        if not nid:
            self._send_json({'error': '无法识别的作品 ID'})
            return
        ids = load_blacklist()
        ids.discard(nid)
        save_blacklist(ids)
        console_log('SCAN', f'Pixiv: 黑名单移除 {nid} (剩 {len(ids)} 个)')
        self._send_json({'ok': True})

    def _handle_blacklist_clear(self):
        """POST /api/blacklist/clear: 保存空集"""
        save_blacklist(set())
        console_log('SCAN', 'Pixiv: 黑名单已清空')
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
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(data)
        except Exception as e:
            console_log('ERROR', f'图片加载失败: {filename} - {e}')
            self._send_error(404, str(e))

    def _handle_log(self, params):
        msg = params.get('msg', [None])[0]
        cat = params.get('cat', ['INFO'])[0]
        if msg:
            console_log(cat, msg)
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
            next_id = LOG_LAST_ID
            truncated = since > 0 and (
                len(items) == 0 or items[0][0] > since or since > next_id
            )
            logs = [{'id': i, 'ts': t, 'cat': c, 'msg': m}
                    for i, t, c, m in items if i > since]
        self._send_json({'logs': logs, 'next_id': next_id, 'truncated': truncated})

    def _handle_logs_clear(self):
        """POST /api/logs/clear: 只清内存缓冲, 不动 sync.log, 计数器不重置"""
        with LOG_LOCK:
            LOG_BUFFER.clear()
        self._send_json({'ok': True})

    def _handle_config(self):
        self._send_json(load_config())

    def _handle_config_save(self):
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length)
        data = json.loads(body)
        save_config(data)
        self._send_json({'ok': True})

# ─── Server ──────────────────────────────────────────────────────────────────

class ThreadedServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    allow_reuse_address = True
    daemon_threads = True

def main():
    server = ThreadedServer(('0.0.0.0', PORT), SyncHandler)

    banner = (
        '+------------------------------------------+\n'
        '|  图片同步 - LAN File Sync                |\n'
        f'|  http://localhost:{PORT}                    |\n'
        '+------------------------------------------+'
    )
    sys.stderr.write(f'{banner}\n')
    sys.stderr.flush()
    console_log('DONE', '服务器就绪')
    log_path = os.path.join(runtime_dir(), 'sync.log')
    sys.stderr.write(f'  日志文件: {log_path}\n')
    sys.stderr.flush()

    webbrowser.open(f'http://localhost:{PORT}')

    def shutdown(sig, frame):
        print('\n  关闭中...')
        server.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\n  关闭中...')
        server.shutdown()

if __name__ == '__main__':
    main()
