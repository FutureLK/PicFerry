/**
 * 图库同步工具 - Gallery Sync Tool
 * 通过局域网 HTTP 在两台手机间同步图片
 * 作者: Sisyphus
 */

const express = require('express');
const http = require('http');
const https = require('https');
const crypto = require('crypto');
const { URL } = require('url');
const { exec } = require('child_process');
const stream = require('stream');
const ftp = require('basic-ftp');

const PORT = 3000;
const IMAGE_EXTS = ['.jpg', '.jpeg', '.png', '.gif', '.webp'];

// ─── Embedded HTML page ─────────────────────────────────────────────────────

const HTML = `<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>图库同步工具</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#0d1117;color:#c9d1d9;min-height:100vh}
.container{max-width:960px;margin:0 auto;padding:24px 16px}
h1{font-size:24px;font-weight:600;color:#58a6ff;margin-bottom:24px;display:flex;align-items:center;gap:10px}
h1 span{font-size:14px;color:#8b949e;font-weight:400}
.card{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:20px;margin-bottom:16px}
.card-title{font-size:14px;font-weight:600;color:#8b949e;margin-bottom:12px;text-transform:uppercase;letter-spacing:.5px}
.input-group{margin-bottom:12px}
.input-group:last-child{margin-bottom:0}
.input-group label{display:block;font-size:13px;color:#8b949e;margin-bottom:4px;font-weight:500}
.input-group input[type="text"]{width:100%;padding:10px 12px;background:#0d1117;border:1px solid #30363d;border-radius:6px;color:#c9d1d9;font-size:14px;font-family:inherit;outline:none;transition:border-color .2s}
.input-group input[type="text"]:focus{border-color:#58a6ff}
.input-group input[type="text"]::placeholder{color:#484f58}
.actions{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:16px}
.btn{display:inline-flex;align-items:center;gap:6px;padding:10px 20px;border:none;border-radius:6px;font-size:14px;font-weight:500;cursor:pointer;transition:all .2s;font-family:inherit}
.btn:disabled{opacity:.5;cursor:not-allowed}
.btn-primary{background:#238636;color:#fff}
.btn-primary:hover:not(:disabled){background:#2ea043}
.btn-primary:active:not(:disabled){background:#1f7a31}
.btn-secondary{background:#21262d;color:#c9d1d9;border:1px solid #30363d}
.btn-secondary:hover:not(:disabled){background:#30363d}
.btn-danger{background:#da3633;color:#fff}
.btn-danger:hover:not(:disabled){background:#f85149}
.btn-danger:active:not(:disabled){background:#b62324}
.toggle-group{display:flex;align-items:center;gap:8px;font-size:13px;color:#8b949e;cursor:pointer;user-select:none;padding:6px 12px;background:#21262d;border-radius:6px;border:1px solid #30363d}
.toggle-group input[type="checkbox"]{width:16px;height:16px;accent-color:#58a6ff;cursor:pointer}
.status{min-height:24px;font-size:14px;color:#8b949e;margin-bottom:12px;padding:8px 12px;background:#0d1117;border-radius:6px;border:1px solid #30363d}
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
tr.fade td{color:#484f58}
.filename{font-family:'SFMono-Regular',Consolas,'Liberation Mono',Menlo,monospace;font-size:13px;word-break:break-all}
.file-hash{font-family:'SFMono-Regular',Consolas,'Liberation Mono',Menlo,monospace;font-size:11px;color:#8b949e}
.summary{font-size:15px;color:#c9d1d9;margin-bottom:12px;padding:12px 16px;background:#0d1117;border-radius:6px;border:1px solid #30363d;text-align:center}
.summary strong{color:#58a6ff}
.progress{background:#0d1117;border-radius:6px;padding:12px 16px;margin-bottom:12px;border:1px solid #30363d;display:none}
.progress.active{display:block}
.progress-bar{height:6px;background:#21262d;border-radius:3px;overflow:hidden;margin-bottom:8px}
.progress-bar-fill{height:100%;background:#238636;width:0%;transition:width .3s;border-radius:3px}
.progress-text{font-size:13px;color:#8b949e}
.empty-state{text-align:center;padding:40px 20px;color:#484f58;font-size:14px}
.empty-state .icon{font-size:48px;margin-bottom:16px}
#syncBtn{margin-top:12px}
.hidden{display:none}
input[type="checkbox"]{accent-color:#58a6ff;cursor:pointer}
</style>
</head>
<body>
<div class="container">
  <h1>📷 图库同步工具 <span>通过局域网 HTTP 同步手机图片</span></h1>

  <div class="card">
    <div class="card-title">📱 设备链接</div>
    <div class="input-group">
      <label for="url1">设备1（主力机 — 目标设备，文件将同步到此设备）</label>
      <input type="text" id="url1" placeholder="http://192.168.1.100:1234/DCIM/Pixez/ 或 ftp://192.168.1.100:21/DCIM/Pixez/">
    </div>
    <div class="input-group">
      <label for="url2">设备2（备用机 — 从此设备扫描新文件）</label>
      <input type="text" id="url2" placeholder="http://192.168.1.101:1234/DCIM/Pixez/ 或 ftp://192.168.1.101:21/DCIM/Pixez/">
    </div>
  </div>

  <div class="actions">
    <button class="btn btn-primary" id="scanBtn">🔍 扫描比对</button>
    <label class="toggle-group">
      <input type="checkbox" id="hashToggle">
      🔒 哈希校验（对同名文件做内容确认）
    </label>
  </div>

  <div class="status" id="status">请输入两台设备的 HTTP/FTP 链接，点击「扫描比对」开始</div>

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
            <th style="width:40px"><input type="checkbox" id="selectAll" title="全选/取消全选"></th>
            <th style="width:40px">#</th>
            <th>文件名</th>
            <th style="width:90px">大小</th>
            <th id="hashTh" style="width:280px" class="hidden">SHA256</th>
          </tr>
        </thead>
        <tbody id="fileList"></tbody>
      </table>
    </div>

    <button class="btn btn-danger" id="syncBtn" disabled>📤 同步到设备1（0 个文件）</button>
  </div>

  <div id="emptyState" class="empty-state">
    <div class="icon">📂</div>
    <div>输入设备链接后点击「扫描比对」查看结果</div>
  </div>
</div>

<script>
const url1 = document.getElementById('url1');
const url2 = document.getElementById('url2');
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

let currentFiles = []; // { filename, size, hash, selected }

function setStatus(msg, type) {
  statusEl.textContent = msg;
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
  const u1 = url1.value.trim();
  const u2 = url2.value.trim();
  if (!u1 || !u2) { setStatus('请填写两台设备的 HTTP 链接', 'error'); return; }

  scanBtn.disabled = true;
  setStatus('🔍 正在扫描设备1...', 'loading');
  showProgress(true);
  setProgress(20, '正在扫描设备1...');
  resultSection.classList.add('hidden');
  emptyState.classList.add('hidden');

  try {
    const [res1, res2] = await Promise.all([
      fetch('/api/list?url=' + encodeURIComponent(u1)),
      fetch('/api/list?url=' + encodeURIComponent(u2))
    ]);

    let [data1, data2] = await Promise.all([res1.json(), res2.json()]);

    if (data1.error) { setStatus('设备1连接失败: ' + data1.error, 'error'); scanBtn.disabled = false; showProgress(false); return; }
    if (data2.error) { setStatus('设备2连接失败: ' + data2.error, 'error'); scanBtn.disabled = false; showProgress(false); return; }

    setProgress(50, '正在比对去重...');

    const files1 = data1.files || [];
    const files2 = data2.files || [];
    const fileNames1 = new Set(files1.map(f => f.name));

    // Filter: files in Device2 that are NOT in Device1 (by filename)
    const uniqueFiles = files2.filter(f => !fileNames1.has(f.name));
    currentFiles = uniqueFiles.map((f, i) => ({ ...f, idx: i, hash: null, selected: true }));

    showProgress(false);

    if (currentFiles.length === 0) {
      setStatus('✅ 设备2中没有找到新文件，两台设备图库完全相同', 'success');
      resultSection.classList.add('hidden');
      emptyState.classList.remove('hidden');
      emptyState.innerHTML = '<div class="icon">✅</div><div>设备2中没有新文件<br>两台设备图库已经同步</div>';
      scanBtn.disabled = false;
      return;
    }

    setStatus(\`✅ 扫描完成 — 设备2有 <strong>\${currentFiles.length}</strong> 个文件是设备1没有的\`, 'success');
    renderTable();
    resultSection.classList.remove('hidden');
    emptyState.classList.add('hidden');

    // Auto-hash if toggle is on
    if (hashToggle.checked) {
      await doHash();
    }
  } catch (e) {
    setStatus('❌ 扫描出错: ' + e.message, 'error');
  }
  scanBtn.disabled = false;
}

function renderTable() {
  let html = '';
  currentFiles.forEach((f, i) => {
    const sizeStr = f.size != null ? formatSize(f.size) : '-';
    html += '<tr class="' + (f.checked === false ? 'fade' : '') + '">';
    html += '<td><input type="checkbox" class="file-cb" data-idx="' + i + '" ' + (f.selected !== false ? 'checked' : '') + '></td>';
    html += '<td>' + (i + 1) + '</td>';
    html += '<td class="filename">' + escapeHtml(f.name) + '</td>';
    html += '<td>' + sizeStr + '</td>';
    html += '<td class="file-hash' + (hashToggle.checked ? '' : ' hidden') + '">' + (f.hash || '—') + '</td>';
    html += '</tr>';
  });
  fileList.innerHTML = html;

  hashTh.classList.toggle('hidden', !hashToggle.checked);
  updateSyncBtn();

  // Checkbox events
  document.querySelectorAll('.file-cb').forEach(cb => {
    cb.addEventListener('change', function() {
      const idx = parseInt(this.dataset.idx);
      if (currentFiles[idx]) currentFiles[idx].selected = this.checked;
      this.closest('tr').classList.toggle('fade', !this.checked);
      updateSyncBtn();
    });
  });
}

function updateSyncBtn() {
  const count = currentFiles.filter(f => f.selected !== false).length;
  syncBtn.textContent = '📤 同步到设备1（' + count + ' 个文件）';
  syncBtn.disabled = count === 0;
}

async function doHash() {
  const u1 = url1.value.trim();
  const u2 = url2.value.trim();
  if (!u1 || !u2) return;

  setProgress(0, '正在计算哈希值...');
  showProgress(true);

  hashTh.classList.remove('hidden');

  for (let i = 0; i < currentFiles.length; i++) {
    const f = currentFiles[i];
    setProgress(Math.round((i / currentFiles.length) * 100), \`计算哈希值 \${i+1}/\${currentFiles.length}: \${f.name}\`);
    try {
      const res = await fetch('/api/hash?url=' + encodeURIComponent(u2) + '&file=' + encodeURIComponent(f.name));
      const data = await res.json();
      if (data.sha256) {
        f.hash = data.sha256.substring(0, 16) + '…';
        // Update table cell
        const row = fileList.querySelector('tr:nth-child(' + (i + 1) + ')');
        if (row) {
          const cell = row.querySelector('.file-hash');
          if (cell) cell.textContent = f.hash;
        }
      }
    } catch (e) {
      // skip hash on error
    }
  }

  showProgress(false);
}

async function doSync() {
  const u1 = url1.value.trim();
  const u2 = url2.value.trim();
  if (!u1 || !u2) { setStatus('请填写设备链接', 'error'); return; }

  const toSync = currentFiles.filter(f => f.selected !== false);
  if (toSync.length === 0) return;

  syncBtn.disabled = true;
  scanBtn.disabled = true;
  showProgress(true);

  let success = 0, fail = 0;

  for (let i = 0; i < toSync.length; i++) {
    const f = toSync[i];
    setProgress(Math.round((i / toSync.length) * 100), \`正在同步 \${i+1}/\${toSync.length}: \${f.name}\`);
    setStatus(\`📤 正在复制 \${f.name}... (\${i+1}/\${toSync.length})\`, 'loading');

    try {
      const res = await fetch('/api/copy?from=' + encodeURIComponent(u2) + '&to=' + encodeURIComponent(u1) + '&file=' + encodeURIComponent(f.name), { method: 'POST' });
      const data = await res.json();
      if (data.success) { success++; }
      else { fail++; console.error('Sync failed:', f.name, data.error); }
    } catch (e) {
      fail++;
      console.error('Sync error:', f.name, e.message);
    }
  }

  showProgress(false);

  if (fail === 0) {
    setStatus(\`✅ 同步完成！成功复制 \${success} 个文件到设备1\`, 'success');
  } else {
    setStatus(\`⚠️ 同步完成：成功 \${success} 个，失败 \${fail} 个。失败的文件请重试\`, 'error');
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

// Event listeners
scanBtn.addEventListener('click', doScan);
hashToggle.addEventListener('change', function() {
  if (currentFiles.length > 0) {
    if (this.checked) doHash();
    else {
      hashTh.classList.add('hidden');
      document.querySelectorAll('.file-hash').forEach(el => el.classList.add('hidden'));
    }
  }
});
selectAll.addEventListener('change', function() {
  currentFiles.forEach(f => f.selected = this.checked);
  document.querySelectorAll('.file-cb').forEach(cb => {
    cb.checked = this.checked;
    cb.closest('tr').classList.toggle('fade', !this.checked);
  });
  updateSyncBtn();
});
syncBtn.addEventListener('click', doSync);

// Initial state
document.getElementById('emptyState').style.display = '';
</script>
</body>
</html>`;

// ─── HTTP fetch helper (Node.js built-in, no external dep) ─────────────────

function httpFetch(urlStr, method = 'GET', bodyStream = null) {
  return new Promise((resolve, reject) => {
    try {
      const parsed = new URL(urlStr);
      const mod = parsed.protocol === 'https:' ? https : http;
      const opts = {
        hostname: parsed.hostname,
        port: parsed.port || (parsed.protocol === 'https:' ? 443 : 80),
        path: parsed.pathname + parsed.search,
        method: method,
        headers: {}
      };

      if (bodyStream) {
        // For PUT with a stream body, we pipe and return status
        const req = mod.request(opts, (res) => {
          let body = '';
          res.on('data', chunk => { body += chunk; });
          res.on('end', () => {
            resolve({ status: res.statusCode, headers: res.headers, body });
          });
        });
        req.on('error', reject);
        bodyStream.pipe(req);
        req.on('close', () => {
          // Only resolve if not already resolved (stream end)
        });
      } else {
        const req = mod.request(opts, (res) => {
          let body = '';
          res.on('data', chunk => { body += chunk; });
          res.on('end', () => {
            resolve({ status: res.statusCode, headers: res.headers, body });
          });
        });
        req.on('error', reject);
        req.setTimeout(15000, () => { req.destroy(new Error('Request timeout')); });
        req.end();
      }
    } catch (e) {
      reject(e);
    }
  });
}

function httpGetStream(urlStr) {
  return new Promise((resolve, reject) => {
    try {
      const parsed = new URL(urlStr);
      const mod = parsed.protocol === 'https:' ? https : http;
      const opts = {
        hostname: parsed.hostname,
        port: parsed.port || (parsed.protocol === 'https:' ? 443 : 80),
        path: parsed.pathname + parsed.search,
        method: 'GET'
      };
      const req = mod.request(opts, (res) => {
        if (res.statusCode >= 400) {
          reject(new Error(`HTTP ${res.statusCode}`));
          return;
        }
        resolve(res); // returns the readable stream
      });
      req.on('error', reject);
      req.setTimeout(30000, () => { req.destroy(new Error('Download timeout')); });
      req.end();
    } catch (e) {
      reject(e);
    }
  });
}

function httpPutBuffer(urlStr, buffer) {
  return new Promise((resolve, reject) => {
    try {
      const parsed = new URL(urlStr);
      const mod = parsed.protocol === 'https:' ? https : http;
      const opts = {
        hostname: parsed.hostname,
        port: parsed.port || (parsed.protocol === 'https:' ? 443 : 80),
        path: parsed.pathname + parsed.search,
        method: 'PUT',
        headers: {
          'Content-Length': buffer.length,
          'Content-Type': 'application/octet-stream'
        }
      };
      const req = mod.request(opts, (res) => {
        let body = '';
        res.on('data', chunk => { body += chunk; });
        res.on('end', () => resolve({ status: res.statusCode, body }));
      });
      req.on('error', reject);
      req.setTimeout(60000, () => req.destroy(new Error('Upload timeout')));
      req.end(buffer);
    } catch (e) {
      reject(e);
    }
  });
}

function httpPutStream(urlStr, stream, contentLength) {
  return new Promise((resolve, reject) => {
    try {
      const parsed = new URL(urlStr);
      const mod = parsed.protocol === 'https:' ? https : http;
      const opts = {
        hostname: parsed.hostname,
        port: parsed.port || (parsed.protocol === 'https:' ? 443 : 80),
        path: parsed.pathname + parsed.search,
        method: 'PUT',
        headers: {}
      };
      if (contentLength) opts.headers['Content-Length'] = contentLength;

      const req = mod.request(opts, (res) => {
        let body = '';
        res.on('data', chunk => { body += chunk; });
        res.on('end', () => {
          resolve({ status: res.statusCode, body });
        });
      });
      req.on('error', reject);
      req.setTimeout(60000, () => { req.destroy(new Error('Upload timeout')); });
      stream.pipe(req);
      stream.on('error', reject);
    } catch (e) {
      reject(e);
    }
  });
}

// ─── Parse phone HTTP directory listing HTML ────────────────────────────────

function parseDirectoryListing(html, baseUrl) {
  const files = [];
  // Match <a href="...">text</a>
  const linkRegex = /<a\s+href="([^"]*)"[^>]*>([^<]*)<\/a>/gi;
  let match;
  while ((match = linkRegex.exec(html)) !== null) {
    const href = match[1].trim();
    const text = match[2].trim();

    // Skip parent directory links and non-file entries
    if (href === '../' || href === './' || href.endsWith('/')) continue;
    if (href.startsWith('?') || href.startsWith('#')) continue;

    const name = text || href;
    const ext = '.' + name.split('.').pop().toLowerCase();

    if (IMAGE_EXTS.includes(ext)) {
      files.push({
        name: name,
        url: resolveUrl(baseUrl, href),
        ext: ext
      });
    }
  }
  return files;
}

function resolveUrl(base, relative) {
  if (relative.startsWith('http://') || relative.startsWith('https://')) return relative;
  const baseStr = base.endsWith('/') ? base : base + '/';
  return baseStr + relative;
}

// ─── FTP helpers ────────────────────────────────────────────────────────────

function parseFtpUrl(urlStr) {
  const parsed = new URL(urlStr);
  return {
    host: parsed.hostname,
    port: parseInt(parsed.port) || 21,
    user: parsed.username || 'anonymous',
    password: parsed.password || 'anonymous@',
    path: parsed.pathname || '/'
  };
}

async function ftpList(ftpUrl) {
  const info = parseFtpUrl(ftpUrl);
  const client = new ftp.Client();
  client.ftp.verbose = false;
  try {
    await client.access({
      host: info.host,
      port: info.port,
      user: info.user,
      password: info.password
    });
    const entries = await client.list(info.path);
    client.close();
    return entries.filter(e => e.type === 1).map(e => ({
      name: e.name,
      size: e.size
    }));
  } catch (e) {
    client.close();
    throw e;
  }
}

async function ftpDownloadBuffer(ftpUrl, filename) {
  const info = parseFtpUrl(ftpUrl);
  const client = new ftp.Client();
  client.ftp.verbose = false;
  try {
    await client.access({
      host: info.host,
      port: info.port,
      user: info.user,
      password: info.password
    });
    const chunks = [];
    const ws = new stream.Writable({
      write(chunk, encoding, cb) {
        chunks.push(chunk);
        cb();
      }
    });
    const remotePath = (info.path.endsWith('/') ? info.path : info.path + '/') + filename;
    await client.downloadTo(ws, remotePath);
    client.close();
    return Buffer.concat(chunks);
  } catch (e) {
    client.close();
    throw e;
  }
}

async function ftpUploadBuffer(ftpUrl, filename, buffer) {
  const info = parseFtpUrl(ftpUrl);
  const client = new ftp.Client();
  client.ftp.verbose = false;
  try {
    await client.access({
      host: info.host,
      port: info.port,
      user: info.user,
      password: info.password
    });
    const rs = new stream.Readable({
      read() {
        this.push(buffer);
        this.push(null);
      }
    });
    const remotePath = (info.path.endsWith('/') ? info.path : info.path + '/') + filename;
    await client.uploadFrom(rs, remotePath);
    client.close();
    return true;
  } catch (e) {
    client.close();
    throw e;
  }
}

// ─── Protocol detection helpers ─────────────────────────────────────────────

function isFtpUrl(urlStr) {
  return urlStr.startsWith('ftp://');
}

async function httpDownloadBuffer(httpUrl) {
  const stream = await httpGetStream(httpUrl);
  return new Promise((resolve, reject) => {
    const chunks = [];
    stream.on('data', chunk => chunks.push(chunk));
    stream.on('end', () => resolve(Buffer.concat(chunks)));
    stream.on('error', reject);
  });
}

function buildFileUrl(baseUrl, filename) {
  const base = baseUrl.endsWith('/') ? baseUrl : baseUrl + '/';
  return base + encodeURIComponent(filename);
}

// ─── Express server ─────────────────────────────────────────────────────────

const app = express();

app.use(express.json());

// Serve the HTML page
app.get('/', (req, res) => {
  res.type('html').send(HTML);
});

// GET /api/list?url=<phone_url>
// Fetch directory listing from phone (HTTP or FTP), parse image filenames
app.get('/api/list', async (req, res) => {
  const phoneUrl = req.query.url;
  if (!phoneUrl) {
    return res.json({ error: 'Missing url parameter' });
  }

  try {
    let files;

    if (isFtpUrl(phoneUrl)) {
      const entries = await ftpList(phoneUrl);
      files = entries.filter(f => {
        const ext = '.' + f.name.split('.').pop().toLowerCase();
        return IMAGE_EXTS.includes(ext);
      });
    } else {
      const response = await httpFetch(phoneUrl);
      if (response.status >= 400) {
        return res.json({ error: `HTTP ${response.status}`, files: [] });
      }
      files = parseDirectoryListing(response.body, phoneUrl);
    }

    res.json({ files, total: files.length });
  } catch (e) {
    res.json({ error: 'Cannot connect to device: ' + e.message, files: [] });
  }
});

// POST /api/hash?url=<phone_url>&file=<filename>
// Download a file from phone (HTTP or FTP) and compute SHA256
app.post('/api/hash', async (req, res) => {
  const phoneUrl = req.query.url;
  const filename = req.query.file;
  if (!phoneUrl || !filename) {
    return res.json({ error: 'Missing url or file parameter' });
  }

  try {
    let buffer;
    if (isFtpUrl(phoneUrl)) {
      buffer = await ftpDownloadBuffer(phoneUrl, filename);
    } else {
      const fileUrl = buildFileUrl(phoneUrl, filename);
      buffer = await httpDownloadBuffer(fileUrl);
    }

    const hash = crypto.createHash('sha256');
    hash.update(buffer);
    res.json({ filename, sha256: hash.digest('hex') });
  } catch (e) {
    res.json({ error: 'File not found: ' + e.message });
  }
});

// POST /api/copy?from=<device2_url>&to=<device1_url>&file=<filename>
// Download file from Device2, upload to Device1 (supports HTTP↔FTP mixed)
app.post('/api/copy', async (req, res) => {
  const fromUrl = req.query.from;
  const toUrl = req.query.to;
  const filename = req.query.file;

  if (!fromUrl || !toUrl || !filename) {
    return res.json({ success: false, error: 'Missing parameters' });
  }

  try {
    // Step 1: Download file from source (Device2)
    let buffer;
    if (isFtpUrl(fromUrl)) {
      buffer = await ftpDownloadBuffer(fromUrl, filename);
    } else {
      const srcUrl = buildFileUrl(fromUrl, filename);
      buffer = await httpDownloadBuffer(srcUrl);
    }

    // Step 2: Upload file to destination (Device1)
    if (isFtpUrl(toUrl)) {
      await ftpUploadBuffer(toUrl, filename, buffer);
      res.json({ success: true, filename });
    } else {
      const dstUrl = buildFileUrl(toUrl, filename);
      const result = await httpPutBuffer(dstUrl, buffer);
      if (result.status >= 200 && result.status < 300) {
        res.json({ success: true, filename });
      } else {
        res.json({ success: false, filename, error: `Device1 returned HTTP ${result.status}` });
      }
    }
  } catch (e) {
    res.json({ success: false, filename, error: e.message });
  }
});

// ─── Start server ──────────────────────────────────────────────────────────

const server = app.listen(PORT, () => {
  const banner = `
╔═══════════════════════════════════════╗
║   图库同步工具 - Gallery Sync Tool    ║
║   http://localhost:${PORT}               ║
╚═══════════════════════════════════════╝`;
  console.log(banner);

  // Auto-open browser on Windows
  if (process.platform === 'win32') {
    exec(`start http://localhost:${PORT}`, (err) => {
      if (err) console.log('  (auto-open failed, open browser manually)');
    });
  }
});

// Graceful shutdown
process.on('SIGINT', () => {
  console.log('\n  Shutting down...');
  server.close(() => process.exit(0));
});
process.on('SIGHUP', () => {
  server.close(() => process.exit(0));
});
