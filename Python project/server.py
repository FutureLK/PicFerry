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

PORT = 13826
IMAGE_EXTS = ('.jpg', '.jpeg', '.png', '.gif', '.webp')

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
        log_dir = os.path.dirname(os.path.abspath(__file__)) if '__file__' in dir() else os.getcwd()
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
/* ─── Thumbnail ─── */
.thumb-wrap{width:48px;height:48px;flex-shrink:0}
.thumb{width:48px;height:48px;object-fit:cover;border-radius:4px;display:block;background:#0d1117}
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
</style>
</head>
<body>
<div class="container">
  <h1>图片同步</h1>
  <div class="subtitle">局域网文件比对与传输</div>

  <!-- ═══ 设备连接 ═══ -->
  <div class="card">
    <div class="input-group">
      <label for="urlA">设备 A（接收端）</label>
      <input type="text" id="urlA" placeholder="http://192.168.1.100:1234/DCIM/Pixez/ 或 ftp://192.168.1.100:21/ 或 C:\Users\...\Pictures">
    </div>
    <div class="input-group">
      <label for="urlB">设备 B（来源端）</label>
      <input type="text" id="urlB" placeholder="http://192.168.1.101:1234/DCIM/ 或 ftp://192.168.1.101:21/ 或 D:\Photos">
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

  <!-- ═══ Pixiv 收藏查重 ═══ -->
  <div class="card">
    <div class="card-title">Pixiv 收藏查重</div>
    <div class="input-group">
      <label for="pixivUid">
        Pixiv UID
        <span class="help-toggle" data-target="helpUid">?</span>
      </label>
      <input type="text" id="pixivUid" placeholder="12345678">
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
      <input type="password" id="pixivPhpsessid" placeholder="浏览器 Cookie 中的 PHPSESSID 值">
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
    </div>

    <div class="actions" style="margin-top:16px;margin-bottom:12px">
      <button class="btn btn-primary" id="pixivFetchBtn">拉取收藏</button>
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
              <th>文件名</th>
              <th style="width:80px">大小</th>
              <th style="width:100px">Illust ID</th>
            </tr>
          </thead>
          <tbody id="pixivFileList"></tbody>
        </table>
      </div>
    </div>
  </div>

  <!-- ═══ 预览面板（在所有标签页之外，避免 position:fixed 嵌套问题）═══ -->
  <div id="previewPanel" class="preview-panel">
    <img id="previewImg" src="" alt="preview">
    <div class="preview-name" id="previewName"></div>
  </div>
</div>

<script>
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
  currentFiles.forEach((f, i) => {
    const sizeStr = f.size != null ? formatSize(f.size) : '-';
    const delay = Math.min(i * 30, 300);
    html += '<tr class="row-enter" style="animation-delay:' + delay + 'ms">';
    html += '<td><input type="checkbox" class="file-cb" data-idx="' + i + '" checked></td>';
    html += '<td>' + (i + 1) + '</td>';
    html += '<td class="thumb-wrap">';
    html += '<img class="thumb" data-src="' + i + '" src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7" alt="" loading="lazy">';
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

function loadThumbnails() {
  const srcUrl = scanDir === 'ab' ? urlB.value.trim() : urlA.value.trim();
  if (!srcUrl) return;
  document.querySelectorAll('.thumb').forEach(img => {
    const idx = parseInt(img.dataset.src);
    const f = currentFiles[idx];
    if (!f) return;
    const src = '/api/image?url=' + encodeURIComponent(srcUrl) + '&file=' + encodeURIComponent(f.name);
    img.src = src;
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
      }, 500);
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

async function doFetchBookmarks() {
  const uid = document.getElementById('pixivUid').value.trim();
  const phpsessid = document.getElementById('pixivPhpsessid').value.trim();
  const path = document.getElementById('pixivPath').value.trim();

  if (!uid || !phpsessid) { setPixivStatus('请填写 Pixiv UID 和 PHPSESSID', 'error'); return; }
  if (!path) { setPixivStatus('请填写本地文件夹路径', 'error'); return; }

  const btn = document.getElementById('pixivFetchBtn');
  btn.disabled = true;
  setPixivStatus('正在拉取 Pixiv 收藏...', 'loading');
  document.getElementById('pixivResult').classList.add('hidden');

  try {
    const res = await fetch('/api/pixiv/bookmarks', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ uid, phpsessid, path })
    });
    const data = await res.json();

    if (data.error) {
      setPixivStatus('错误: ' + data.error, 'error');
      return;
    }

    document.getElementById('pixivTotal').textContent = data.total_bookmarks ?? 0;
    document.getElementById('pixivLocalCount').textContent = data.local_count ?? 0;
    document.getElementById('pixivMatched').textContent = data.matched_count ?? 0;

    const tbody = document.getElementById('pixivFileList');
    const matched = data.matched || [];
    if (matched.length > 0) {
      let html = '';
      matched.forEach((f, i) => {
        const sizeStr = f.size != null ? formatSize(f.size) : '-';
        html += '<tr>';
        html += '<td>' + (i + 1) + '</td>';
        html += '<td class="filename">' + escapeHtml(f.name) + '</td>';
        html += '<td>' + sizeStr + '</td>';
        html += '<td>' + escapeHtml(f.illust_id || '') + '</td>';
        html += '</tr>';
      });
      tbody.innerHTML = html;
    } else {
      tbody.innerHTML = '<tr><td colspan="4" style="text-align:center;color:#484f58;padding:20px">没有找到匹配的文件</td></tr>';
    }

    document.getElementById('pixivResult').classList.remove('hidden');
    if (matched.length > 0) {
      setPixivStatus('查重完成，发现 ' + matched.length + ' 个已在 Pixiv 收藏的文件', 'success');
    } else {
      setPixivStatus('查重完成，本地文件均不在 Pixiv 收藏中', 'success');
    }
  } catch (e) {
    setPixivStatus('请求失败: ' + e.message, 'error');
  }
  btn.disabled = false;
}

document.getElementById('pixivFetchBtn').addEventListener('click', doFetchBookmarks);

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

def fetch_all_pixiv_bookmark_ids(uid, phpsessid):
    """Fetch all bookmark illust IDs (public + private) from Pixiv."""
    all_ids = set()
    request_count = 0

    for visibility in ('show', 'hide'):
        offset = 0
        limit = 100

        while True:
            params = urllib.parse.urlencode({
                'tag': '', 'offset': offset, 'limit': limit, 'rest': visibility
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
            if not works:
                break

            for work in works:
                all_ids.add(str(work.get('id', '')))

            total = data.get('body', {}).get('total', 0)
            request_count += 1
            console_log('SCAN', f'Pixiv({visibility}): {len(all_ids)}/{total} 请求{request_count}次')

            offset += limit
            if offset >= total:
                break

            time.sleep(0.8)  # rate limit

    return sorted(all_ids)


def extract_illust_id(filename):
    """Extract Pixiv illust ID from filename like '114514_p0.jpg'."""
    m = re.match(r'^(\d+)_p\d+', filename)
    if m:
        return m.group(1)
    return None


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
        elif parsed.path == '/api/log':
            self._handle_log(params)
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
            # 1. Fetch bookmarks
            console_log('SCAN', f'Pixiv: 开始拉取收藏 (UID={uid})')
            illust_ids = fetch_all_pixiv_bookmark_ids(uid, phpsessid)
            console_log('DONE', f'Pixiv: 拉取完成, 共 {len(illust_ids)} 个收藏')

            # 2. Scan local path
            console_log('SCAN', f'Pixiv: 扫描本地路径 {local_path}')
            local_files = []
            if is_local_path(local_path):
                local_files = local_list(local_path)
            elif is_ftp(local_path):
                entries = ftp_list(local_path)
                local_files = [e for e in entries
                               if os.path.splitext(e['name'])[1].lower() in IMAGE_EXTS]
            else:
                body_text, status = http_fetch(local_path)
                entries = parse_html_listing(body_text)
                local_files = entries

            # 3. Match
            matched = []
            for f in local_files:
                illust_id = extract_illust_id(f['name'])
                if illust_id and illust_id in illust_ids:
                    matched.append({
                        'name': f['name'],
                        'size': f.get('size', 0),
                        'illust_id': illust_id
                    })

            console_log('DONE', f'Pixiv: 本地 {len(local_files)} 文件, 匹配 {len(matched)} 个')

            self._send_json({
                'total_bookmarks': len(illust_ids),
                'local_count': len(local_files),
                'matched_count': len(matched),
                'matched': matched[:1000],
            })

        except urllib.error.HTTPError as e:
            if e.code == 403:
                self._send_json({'error': 'Pixiv 认证失败，请检查 PHPSESSID 是否有效或已过期'})
            elif e.code == 404:
                self._send_json({'error': 'Pixiv 用户不存在，请检查 UID'})
            else:
                self._send_json({'error': f'HTTP {e.code}'})
        except Exception as e:
            console_log('ERROR', f'Pixiv 查重失败: {e}')
            self._send_json({'error': str(e)})

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
    log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)) if '__file__' in dir() else os.getcwd(), 'sync.log')
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
