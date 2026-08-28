
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
let hashJobSeq = 0;      // 哈希任务世代计数器: 取消/重扫/切向/同步都会 ++, 旧循环失配即静默退出
let progressOwner = null; // 进度条归属: 'hash' | 'scan' | 'sync' | null（单写者, 防误收）

// ─── Config auto-fill & save ───────────────────────────────────
let globalConfig = null;   // 供设置 tab / 预览延迟 / 缩略图尺寸读取
let debugModeOn = false;   // debug 诊断开关镜像: 开启期间前端以 [DEBUG] 上报动作耗时

function applyTheme(light) {
  // 日间模式开关: html[data-theme=light] 触发 CSS 浅色变量覆盖层
  if (light) document.documentElement.setAttribute('data-theme', 'light');
  else document.documentElement.removeAttribute('data-theme');
}

async function loadConfig() {
  try {
    const res = await fetch('/api/config');
    const cfg = await res.json();
    globalConfig = cfg;
    if (cfg.dev1ceA) urlA.value = cfg.dev1ceA;
    if (cfg.dev1ceB) urlB.value = cfg.dev1ceB;
    if (cfg.PixivUID) document.getElementById('pixivUid').value = cfg.PixivUID;
    if (cfg.PixivL) document.getElementById('pixivPath').value = cfg.PixivL;
    if (cfg.pixivLimit != null) document.getElementById('pixivLimit').value = cfg.pixivLimit;
    // 缩略图尺寸联动: CSS 变量 --thumb-size
    const ts = parseInt(cfg.thumbnailSize) || 48;
    document.documentElement.style.setProperty('--thumb-size', ts + 'px');
    applyTheme(cfg.lightTheme);
    // 设置 tab 控件填充
    fillSettingsControls();
  } catch (e) {
    // config 文件不存在或解析失败，静默忽略
    fillSettingsControls();
  }
}

async function saveConfig() {
  const data = {
    dev1ceA: urlA.value.trim(),
    dev1ceB: urlB.value.trim(),
    PixivUID: document.getElementById('pixivUid').value.trim(),
    PixivL: document.getElementById('pixivPath').value.trim(),
    pixivLimit: document.getElementById('pixivLimit').value.trim(),
    thumbnailSize: settingThumbSize.value,
    previewDelay: settingPreviewDelay.value,
    pixivInterval: settingPixivInterval.value,
    maxRows: settingMaxRows.value,
    lightTheme: settingTheme.value === '1' ? 1 : 0,
    debugMode: settingDebug.value === '1' ? 1 : 0,
  };
  const _p = document.getElementById('pixivPhpsessid').value.trim();
  if (_p) data.PHPSESSID = _p;
  const _t0 = performance.now();
  try {
    await fetch('/api/config/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    debugTime('配置保存', _t0);
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
    if ((el === urlA || el === urlB) && !el.value.trim()) { showEmptyState(); }
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
  fetch('/api/log?cat=' + encodeURIComponent(cat) + '&msg=' + encodeURIComponent(msg), { method: 'POST' }).catch(() => {});
}

function debugLog(msg) {
  // debug 诊断: 仅开关开启期间上报, 走 /api/log 统一双通道(stderr + 网页面板)
  if (debugModeOn) logToServer('DEBUG', msg);
}

function debugTime(label, t0) {
  // 统一格式: [DEBUG] 动作描述: N ms(毫秒整数)
  debugLog(label + ': ' + Math.round(performance.now() - t0) + ' ms');
}

function setStatus(msg, type) {
  statusEl.textContent = msg;
  statusEl.className = 'status' + (type ? ' ' + type : '');
}

function showProgress(show) {
  progressWrap.classList.toggle('active', show);
}

// 恢复空态提示并隐藏结果区与同步按钮（扫描失败 / 输入清空时调用）
function showEmptyState() {
  emptyState.classList.remove('hidden');
  resultSection.classList.add('hidden');
  syncBtn.classList.add('hidden');
}

function setProgress(pct, text) {
  progressFill.style.width = pct + '%';
  progressText.textContent = text;
}

async function doScan() {
  const u1 = urlA.value.trim();
  const u2 = urlB.value.trim();
  if (!u1 || !u2) { setStatus('请填写两台设备的链接或路径', 'error'); return; }

  // 失焦自动保存可能尚未落盘: 先等保存完成——新输入的本地盘路径必须先成为
  // 「已声明基座」才可通过服务端扫描校验(网络地址不受影响)
  await saveConfig();

  scanBtn.disabled = true;
  emptyState.classList.add('hidden');
  setStatus('正在扫描设备 A...', 'loading');
  showProgress(true);
  progressOwner = 'scan';
  setProgress(20, '');   // 统一视觉: 文案只走状态栏, 进度条为纯附属
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

    if (data1.error) { setStatus('设备 A 连接失败: ' + data1.error, 'error'); showEmptyState(); scanBtn.disabled = false; showProgress(false); progressOwner = null; return; }
    if (data2.error) { setStatus('设备 B 连接失败: ' + data2.error, 'error'); showEmptyState(); scanBtn.disabled = false; showProgress(false); progressOwner = null; return; }

    loadedFilesA = data1.files || [];
    loadedFilesB = data2.files || [];

    setStatus('正在比对去重...', 'loading');
    setProgress(50, '');

    // 显示设备统计
    renderStats(loadedFilesA, loadedFilesB);

    // 去重
    runDedup();

    showProgress(false);
    progressOwner = null;

    if (currentFiles.length === 0) {
      if (scanDir === 'ab') {
        setStatus('扫描完成，设备 B 中没有发现新文件', 'success');
      } else {
        setStatus('扫描完成，设备 A 中没有发现新文件', 'success');
      }
      logToServer('DONE', '扫描完成，无新文件');
      syncBtn.classList.add('hidden');
      scanBtn.disabled = false;
      return;
    }

    const dirLabel = scanDir === 'ab' ? 'B→A' : 'A→B';
    setStatus('扫描完成，' + dirLabel + ' 方向有 ' + currentFiles.length + ' 个文件待同步', 'success');
    logToServer('DONE', '发现 ' + currentFiles.length + ' 个待同步文件');
    renderTable();
    resultSection.classList.remove('hidden');
    syncBtn.classList.remove('hidden');
    syncBtn.classList.remove('slide-in');
    void syncBtn.offsetWidth;
    syncBtn.classList.add('slide-in');

    if (hashToggle.checked) {
      await doHash();
    }
  } catch (e) {
    setStatus('扫描出错: ' + e.message, 'error');
    showEmptyState();
    showProgress(false);
    progressOwner = null;
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
  hashJobSeq++;
  if (progressOwner === 'hash') { showProgress(false); progressOwner = null; }
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
  const _t0 = performance.now();
  const RENDER_LIMIT = parseInt((globalConfig || {}).maxRows) || 1000;
  let html = '';
  const srcUrl = scanDir === 'ab' ? urlB.value.trim() : urlA.value.trim();
  currentFiles.forEach((f, i) => {
    if (i >= RENDER_LIMIT) return;
    const sizeStr = f.size != null ? formatSize(f.size) : '-';
    const delay = Math.min(i * 30, 300);
    const thumbUrl = srcUrl ? '/api/image?url=' + encodeURIComponent(srcUrl) + '&file=' + encodeURIComponent(f.name) : '';
    html += '<tr class="row-enter" data-idx="' + i + '" style="animation-delay:' + delay + 'ms">';
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
  if (currentFiles.length > RENDER_LIMIT) { html += '<tr><td colspan="6" style="padding:10px;text-align:center;color:var(--text-muted)">仅显示前 ' + RENDER_LIMIT + ' 行（共 ' + currentFiles.length + ' 个文件，同步不受影响）</td></tr>'; }
  thumbObserver.disconnect();
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
  debugTime('结果表渲染 ' + currentFiles.length + ' 行', _t0);
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

// ─── Preview hover ─────────────────────────────────────────────────────

let previewTimer = null;
let previewSeq = 0;        // 预览代数: 换行/离开即 ++, 迟到的图片 onload 失配即丢弃
let lastPreviewUrl = '';   // 上次预览地址: 同图重复 hover 时浏览器不再触发 onload, 需直接显示
const previewPanel = document.getElementById('previewPanel');
const previewImg = document.getElementById('previewImg');
const previewName = document.getElementById('previewName');

function bindPreviewHover() {
  document.querySelectorAll('#fileList .thumb-wrap, #fileList .filename').forEach(link => {
    link.addEventListener('mouseenter', function(e) {
      const idx = parseInt(this.closest('tr').dataset.idx);
      const f = currentFiles[idx];
      if (!f) return;
      const srcUrl = scanDir === 'ab' ? urlB.value.trim() : urlA.value.trim();
      if (!srcUrl) return;

      // 预览延迟可配置 (config previewDelay, 默认 500ms); null 保护防 loadConfig 未完成
      const delay = parseInt((globalConfig || {}).previewDelay) || 500;
      previewTimer = setTimeout(() => {
        const _t0 = performance.now();
        const rect = this.getBoundingClientRect();
        previewName.textContent = f.name + (f.size != null ? ' (' + formatSize(f.size) + ')' : '');
        const url = '/api/image?url=' + encodeURIComponent(srcUrl) + '&file=' + encodeURIComponent(f.name);
        const seq = ++previewSeq;
        // 图片加载完成才显示面板(防未就绪空框), 再定位
        const show = function() {
          if (seq !== previewSeq) return;   // 迟到的加载: 已换行/已离开, 丢弃
          debugTime('预览加载 ' + f.name, _t0);   // 同图捷径(L441)直显时≈0ms, 语义为缓存命中
          previewPanel.classList.add('active');
          const panelH = previewPanel.offsetHeight || 480;

          // Position: below the link, or above if near bottom
          let top = rect.bottom + 8;
          if (top + panelH > window.innerHeight) {
            top = rect.top - 8 - panelH;
          }
          let left = Math.min(rect.left, window.innerWidth - 420);
          previewPanel.style.top = Math.max(8, top) + 'px';
          previewPanel.style.left = Math.max(8, left) + 'px';
        };
        if (lastPreviewUrl === url) { show(); return; }
        lastPreviewUrl = url;
        previewImg.onload = show;
        previewImg.onerror = function() {
          // 加载失败不显示(防破图空框); 回滚缓存地址, 否则再次悬停会命中
          // "同图免 onload 直显"捷径, 弹出失败残留的破图面板
          lastPreviewUrl = '';
        };
        previewImg.src = url;
      }, delay);
    });

    link.addEventListener('mouseleave', function(e) {
      const rel = e.relatedTarget;
      if (rel && rel.closest && rel.closest('.thumb-wrap, .filename')) {
        clearTimeout(previewTimer);
        return;
      }
      clearTimeout(previewTimer);
      previewSeq++;
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

function syncHashColumn() {
  hashTh.classList.toggle('hidden', !hashToggle.checked);
  document.querySelectorAll('.file-hash').forEach(el => el.classList.toggle('hidden', !hashToggle.checked));
}

async function doHash() {
  const srcUrl = scanDir === 'ab' ? urlB.value.trim() : urlA.value.trim();
  if (!srcUrl) return;

  setProgress(0, '正在计算哈希值...');
  showProgress(true);
  if (!hashToggle.checked || currentFiles.length === 0) {
    // 早退守卫: 此处 progressOwner 尚未被本函数认领（claim 在守卫之后）
    // - 'scan'/'sync' 在途: 静默返回, 绝不碰他人进度条（扫描在途勾选哈希绝不影响 scan 进度条）
    // - null（无在途任务）: 本 doHash 刚 showProgress(true) 显示了进度条, 勾选态异常/无文件 → 隐藏防残留空进度条
    if (progressOwner === null) { showProgress(false); }
    return;
  }
  const job = ++hashJobSeq;
  // 进度条归属认领: 仅当无任何在途任务(null)时才认领 'hash'——scan/sync 在途均不劫持
  // （同步在途勾选哈希: 不认领 → 哈希完成时 if(progressOwner==='hash') 为假 → 不提前隐藏同步进度条）
  if (progressOwner === null) progressOwner = 'hash';
  logToServer('HASH', '开始哈希校验 ' + currentFiles.length + ' 个文件');

  for (let i = 0; i < currentFiles.length; i++) {
    const f = currentFiles[i];
    if (job !== hashJobSeq) return;
    if (f.hash) continue;
    setProgress(Math.round((i / currentFiles.length) * 100), '计算哈希值 ' + (i+1) + '/' + currentFiles.length + ': ' + f.name);
    try {
      const res = await fetch('/api/hash?url=' + encodeURIComponent(srcUrl) + '&file=' + encodeURIComponent(f.name), { method: 'POST' });
      const data = await res.json();
      if (job !== hashJobSeq) return;
      if (data.sha256) {
        f.hash = data.sha256.substring(0, 16) + '...';
        const row = fileList.querySelector('tr:nth-child(' + (i + 1) + ')');
        if (row) {
          const cell = row.querySelector('.file-hash');
          if (cell) { cell.textContent = f.hash; if (hashToggle.checked) cell.classList.remove('hidden'); }
        }
      }
    } catch (e) {
      // skip
    }
  }
  if (progressOwner === 'hash') { showProgress(false); progressOwner = null; }
  syncHashColumn();
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
  hashJobSeq++;
  progressOwner = 'sync';
  logToServer('SYNC', '开始同步 ' + toSync.length + ' 个文件 (' + dirLabel + ')');

  let success = 0, fail = 0;

  for (let i = 0; i < toSync.length; i++) {
    const f = toSync[i];
    setProgress(Math.round((i / toSync.length) * 100), '');   // 统一视觉: 同步文案只走状态栏
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

  if (progressOwner === 'sync') { showProgress(false); progressOwner = null; }

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

  if (!uid) { setPixivStatus('请填写 Pixiv UID', 'error'); return; }
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
  const _t0 = performance.now();
  document.getElementById('pixivTotal').textContent = summary ? (summary.total_bookmarks ?? 0) : 0;
  document.getElementById('pixivMissing').textContent = summary ? (summary.missing_works ?? 0) : 0;
  document.getElementById('pixivMissingPages').textContent = summary ? (summary.missing_pages ?? 0) : 0;

  const tbody = document.getElementById('pixivFileList');
  if (matched.length > 0) {
    let html = '';
    matched.forEach((f, i) => {
      html += '<tr>';
      html += '<td>' + (i + 1) + '</td>';
      html += '<td class="filename">' + escapeHtml(f.illust_id + '_' + f.range) + '</td>';
      html += '<td><button class="btn blk-add" style="padding:2px 7px;font-size:11px" data-id="' + escapeHtml(f.illust_id) + '">加黑名单</button></td>';
      // escapeHtml 基于 textContent→innerHTML，不转义引号；href 属性上下文须再补 &quot;（防 " 逃逸属性注入）
      html += '<td><a href="' + escapeHtml('https://www.pixiv.net/artworks/' + f.illust_id).replace(/"/g, '&quot;') + '" target="_blank" rel="noopener noreferrer">' + escapeHtml(f.illust_id).replace(/"/g, '&quot;') + '</a></td>';
      html += '<td>已有' + f.saved_pages + '张/共' + f.pageCount + '张</td>';
      html += '</tr>';
    });
    tbody.innerHTML = html;

    // 加黑名单按钮: 行保留 + 变暗标记; 进入即 disabled（双击防护）; 成功保持 disabled
    document.querySelectorAll('#pixivFileList .blk-add').forEach(btn => {
      btn.addEventListener('click', async function() {
        btn.disabled = true;
        try {
          const res = await fetch('/api/blacklist/add', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id: btn.dataset.id })
          });
          const data = await res.json();
          if (data.ok || !data.error) {
            btn.closest('tr').classList.add('row-blacklisted');
            btn.textContent = '已加入';
            loadBlacklistUI();
          } else {
            btn.disabled = false;
            setPixivStatus('添加黑名单失败: ' + (data.error || ''), 'error');
          }
        } catch (e) {
          btn.disabled = false;
          setPixivStatus('添加黑名单失败: ' + (e.message || ''), 'error');
        }
      });
    });
    syncPixivRowsWithBlacklist();   // 渲染后按最新名单对齐(覆盖"渲染时 ID 已在黑名单"的边界)
  } else {
    tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--text-dim);padding:20px">没有缺失作品</td></tr>';
  }
  document.getElementById('pixivResult').classList.remove('hidden');
  if (matched.length > 0) {
    setPixivStatus('查重完成，发现 ' + (summary?.missing_works ?? matched.length) + ' 个缺失作品（缺失分p ' + (summary?.missing_pages ?? 0) + ' 张）', 'success');
  } else {
    setPixivStatus('没有缺失作品，收藏完整', 'success');
  }
  debugTime('Pixiv 结果渲染 ' + matched.length + ' 行', _t0);
}

function stopPixivJob() {
  fetch('/api/pixiv/bookmarks/stop', { method: 'POST' }).catch(() => {});
  setPixivStatus('正在终止…', 'loading');
}

document.getElementById('pixivFetchBtn').addEventListener('click', doFetchBookmarks);
document.getElementById('pixivStopBtn').addEventListener('click', stopPixivJob);

scanBtn.addEventListener('click', doScan);
hashToggle.addEventListener('change', function() {
  if (this.checked) {
    hashJobSeq++;
    syncHashColumn();
    doHash();
  } else {
    hashJobSeq++;
    syncHashColumn();
    if (progressOwner === 'hash') { showProgress(false); progressOwner = null; }
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
const CATS = ['SCAN', 'HASH', 'SYNC', 'IMAGE', 'DONE', 'ERROR', 'BLACKLIST', 'DEBUG'];

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
const settingTheme = document.getElementById('settingTheme');
const settingPreviewDelay = document.getElementById('settingPreviewDelay');
const settingPixivInterval = document.getElementById('settingPixivInterval');
const settingMaxRows = document.getElementById('settingMaxRows');
const settingDebug = document.getElementById('settingDebug');

// 缩略图尺寸档位（与 settingThumbSize 下拉选项一致）
const THUMB_PRESETS = [16, 24, 48, 64, 96];

function fillSettingsControls() {
  const cfg = globalConfig || {};
  // 历史滑条遗留的档位外数值: 动态补"自定义"选项保证回显（loadConfig 启动时只调用一次）
  if (cfg.thumbnailSize != null && !THUMB_PRESETS.includes(parseInt(cfg.thumbnailSize))) {
    // 已存在同名 value 则跳过, 防二次调用时重复追加
    const customVal = String(cfg.thumbnailSize);
    if (![...settingThumbSize.options].some(o => o.value === customVal)) {
      const opt = document.createElement('option');
      opt.value = customVal;
      opt.textContent = '自定义（' + cfg.thumbnailSize + 'px）';
      settingThumbSize.appendChild(opt);
    }
  }
  settingThumbSize.value = cfg.thumbnailSize != null ? cfg.thumbnailSize : 48;
  settingPreviewDelay.value = cfg.previewDelay != null ? cfg.previewDelay : 500;
  settingPixivInterval.value = cfg.pixivInterval != null ? cfg.pixivInterval : 0.8;
  settingMaxRows.value = cfg.maxRows != null ? cfg.maxRows : 1000;
  settingTheme.value = cfg.lightTheme ? '1' : '0';
  settingDebug.value = cfg.debugMode ? '1' : '0';
  debugModeOn = !!cfg.debugMode;
}

// 缩略图/主题下拉: change 即联动生效, 持久化由下方统一 blur/change 绑定完成
settingThumbSize.addEventListener('change', function() {
  document.documentElement.style.setProperty('--thumb-size', this.value + 'px');
});
settingTheme.addEventListener('change', function() {
  applyTheme(this.value === '1');
});
settingDebug.addEventListener('change', function() {
  debugModeOn = this.value === '1';   // debug 门控即时生效, 持久化由下方统一绑定完成
});
[settingThumbSize, settingTheme, settingPreviewDelay, settingPixivInterval, settingMaxRows, settingDebug].forEach(el => {
  el.addEventListener('blur', saveConfig);
  el.addEventListener('change', saveConfig);
});

// 黑名单管理
const blacklistList = document.getElementById('blacklistList');
let currentBlacklist = new Set();   // 最新黑名单集合缓存: 供 Pixiv 结果行双向同步

// Pixiv 结果行与黑名单双向同步: 在名单→变暗+已加入+禁用, 不在→恢复可点
function syncPixivRowsWithBlacklist() {
  document.querySelectorAll('#pixivFileList .blk-add').forEach(btn => {
    const inList = currentBlacklist.has(btn.dataset.id);
    btn.closest('tr').classList.toggle('row-blacklisted', inList);
    btn.textContent = inList ? '已加入' : '加黑名单';
    btn.disabled = inList;
  });
}

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
      currentBlacklist = new Set();
      syncPixivRowsWithBlacklist();
      blacklistList.innerHTML = '<div style="color:var(--text-dim);font-size:13px;padding:8px 0">黑名单为空</div>';
      return;
    }
    currentBlacklist = new Set(ids);
    blacklistList.innerHTML = ids.map(id =>
      '<div style="display:flex;align-items:center;justify-content:space-between;padding:6px 8px;border-bottom:1px solid var(--bg-inset);font-family:monospace;font-size:13px">' +
      '<span>' + escapeHtml(id) + '</span>' +
      '<button class="btn btn-danger" style="padding:4px 12px;font-size:12px" data-remove="' + escapeHtml(id).replace(/"/g, '&quot;') + '">删除</button>' +
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
    syncPixivRowsWithBlacklist();
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

// 清空黑名单双击确认(破坏性操作): 首点进入待确认态, 3 秒内再点才执行, 超时自动复位
let clearArmTimer = null;
document.getElementById('blacklistClearBtn').addEventListener('click', async function() {
  if (!this.dataset.armed) {
    this.dataset.armed = '1';
    this.textContent = '再点一次确认';
    clearTimeout(clearArmTimer);
    clearArmTimer = setTimeout(() => {
      delete this.dataset.armed;
      this.textContent = '清空';
    }, 3000);
    return;
  }
  clearTimeout(clearArmTimer);
  delete this.dataset.armed;
  this.textContent = '清空';
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
