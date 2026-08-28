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

PORT = 13826


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

# ─── Embedded HTML ───────────────────────────────────────────────────────────

HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>PicFerry</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
/* ─── 主题变量 ─────────────────────────────────────────────
   深色为默认；[data-theme=light] 为日间模式覆盖层。
   新增颜色规则一律引用变量，禁止再写硬编码 hex（内联样式也用 var()） */
:root{
  color-scheme:dark;
  --bg:#0d1117;           /* 页面底色 / 输入框与嵌入面板深底 */
  --bg-card:#161b22;      /* 卡片 / 浮层 */
  --bg-inset:#21262d;     /* 次级底：表头、开关、进度槽、code */
  --bg-hover:#1c2128;     /* 表格行悬停 */
  --border:#30363d;
  --shadow:rgba(0,0,0,.6);
  --text:#c9d1d9;
  --text-strong:#e6edf3;
  --text-muted:#8b949e;
  --text-dim:#484f58;
  --accent:#58a6ff;       /* 强调蓝：focus 链接 loading 等 */
  --accent-solid:#1f6feb; /* 实心强调块：方向切换选中 帮助球悬停 */
  --ok:#3fb950;           /* 成功绿文本 徽标 */
  --ok-solid:#238636;     /* 主按钮底色 */
  --ok-hover:#2ea043;
  --err:#f85149;          /* 错误红文本 徽标 */
  --err-hover:#f85149;    /* 危险按钮悬停 */
  --err-solid:#da3633;
  --warn:#d29922;
  --cyan:#39c5cf;         /* 日志分类 SCAN */
  --violet:#bc8cff;       /* 日志分类 BLACKLIST */
}
html[data-theme="light"]{
  color-scheme:light;
  --bg:#ffffff;
  --bg-card:#f6f8fa;
  --bg-inset:#eaeef2;
  --bg-hover:#f3f4f6;
  --border:#d0d7de;
  --shadow:rgba(31,35,40,.18);
  --text:#1f2328;
  --text-strong:#1f2328;
  --text-muted:#656d76;
  --text-dim:#8c959f;
  --accent:#0969da;
  --accent-solid:#0969da;
  --ok:#1a7f37;
  --ok-solid:#1f883d;
  --ok-hover:#1a7f37;
  --err:#cf222e;
  --err-hover:#a40626;
  --err-solid:#cf222e;
  --warn:#9a6700;
  --cyan:#1b7c83;
  --violet:#8250df;
}
/* 全局缩放系数：按参考站 benchmark.leoblack.top 实测字号比（表格 0.92rem≈14.7px vs 本应用 13px≈1.13）取 1.15；容器宽度不追平基准站 1320px；如需调整只改这一处 */
html{zoom:1.15}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:var(--bg);color:var(--text);min-height:100vh}
.container{max-width:960px;margin:0 auto;padding:24px 16px}
.card{background:var(--bg-card);border:1px solid var(--border);border-radius:8px;padding:20px;margin-bottom:16px}
.card-title{font-size:13px;font-weight:600;color:var(--text-muted);margin-bottom:12px;letter-spacing:.3px}
.input-group{margin-bottom:12px}
.input-group:last-child{margin-bottom:0}
.input-group label{display:block;font-size:13px;color:var(--text-muted);margin-bottom:4px;font-weight:500}
/* 统一控件皮肤：除勾选框外的所有 input 与 select 全命中，
   未来新增 input 类型自动继承，不会再漏涂成系统默认白底 */
.input-group input:not([type="checkbox"]):not([type="range"]),
.input-group select{padding:10px 12px;background:var(--bg);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:14px;font-family:inherit;outline:none;transition:border-color .2s}
.input-group select{cursor:pointer}
.input-group input:not([type="checkbox"]):not([type="range"]):focus,
.input-group select:focus{border-color:var(--accent)}
.input-group input:not([type="checkbox"]):not([type="range"])::placeholder{color:var(--text-dim)}
/* 宽度单独控制：文本类占满整行，数字框保持默认窄宽与单位（ms/s）同行 */
.input-group input[type="text"],
.input-group input[type="password"],
.input-group select{width:100%}
.actions{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:16px}
.btn{display:inline-flex;align-items:center;gap:6px;padding:10px 20px;border:none;border-radius:6px;font-size:14px;font-weight:500;cursor:pointer;transition:all .2s;font-family:inherit}
.btn:disabled{opacity:.5;cursor:not-allowed}
.btn-primary{background:var(--ok-solid);color:#fff}
.btn-primary:hover:not(:disabled){background:var(--ok-hover)}
.btn-danger{background:var(--err-solid);color:#fff}
.btn-danger:hover:not(:disabled){background:var(--err-hover)}
.btn:active:not(:disabled){transform:scale(.97)}
.toggle-group{display:flex;align-items:center;gap:8px;font-size:13px;color:var(--text-muted);cursor:pointer;user-select:none;padding:6px 12px;background:var(--bg-inset);border-radius:6px;border:1px solid var(--border)}
.toggle-group input[type="checkbox"]{width:16px;height:16px;accent-color:var(--accent);cursor:pointer}
.status{min-height:24px;font-size:14px;color:var(--text-muted);margin-bottom:12px;padding:8px 12px;background:var(--bg);border-radius:6px;border:1px solid var(--border);transition:color .3s,border-color .3s}
.status.success{color:var(--ok);border-color:var(--ok-solid)}
.status.error{color:var(--err);border-color:var(--err-solid)}
.status.loading{color:var(--accent);border-color:var(--accent)}
.table-wrap{overflow-x:auto;border:1px solid var(--border);border-radius:6px}
table{width:100%;border-collapse:collapse;font-size:13px}
thead{background:var(--bg-inset)}
th{text-align:left;padding:10px 12px;color:var(--text-muted);font-weight:600;border-bottom:1px solid var(--border);white-space:nowrap}
td{padding:8px 12px;border-bottom:1px solid var(--bg-inset);vertical-align:middle}
tr:last-child td{border-bottom:none}
tr:hover td{background:var(--bg-hover)}
tr.row-blacklisted{opacity:.55}
.filename{font-family:'SFMono-Regular',Consolas,'Liberation Mono',Menlo,monospace;font-size:13px;word-break:break-all}
.file-hash{font-family:'SFMono-Regular',Consolas,'Liberation Mono',Menlo,monospace;font-size:11px;color:var(--text-muted)}
.progress{background:var(--bg);border-radius:6px;padding:12px 16px;margin-bottom:12px;border:1px solid var(--border);display:none}
.progress.active{display:block}
.progress-bar{height:6px;background:var(--bg-inset);border-radius:3px;overflow:hidden}
.progress-bar-fill{height:100%;background:var(--ok-solid);width:0%;transition:width .3s;border-radius:3px}
.progress-text{font-size:13px;color:var(--text-muted);margin-top:8px}
.progress-text:empty{display:none}   /* 无文字阶段(扫描/同步)不留死区: 进度框收窄且 bar 垂直居中 */
.empty-state{text-align:center;padding:40px 20px;color:var(--text-dim);font-size:14px}
.input-hint{font-size:12px;color:var(--text-dim);margin-top:2px}
.input-badge{font-size:11px;margin-top:2px;color:var(--text-dim);min-height:14px}
.input-badge.http{color:var(--accent)}
.input-badge.ftp{color:var(--warn)}
.input-badge.local{color:var(--ok)}
.input-badge.invalid{color:var(--err)}
.input-badge.error{color:var(--err)}
.input-badge.success{color:var(--ok)}
/* ─── Settings grid（界面设置两列布局，窄屏回退单列）─── */
.settings-grid{display:grid;grid-template-columns:1fr 1fr;gap:0 16px}
@media (max-width:720px){.settings-grid{grid-template-columns:1fr}}
/* ─── Stats bar ─── */
.stats{display:flex;gap:16px;margin-bottom:12px;flex-wrap:wrap}
.stat-item{flex:1;min-width:180px;background:var(--bg);border:1px solid var(--border);border-radius:6px;padding:10px 14px}
.stat-label{font-size:11px;color:var(--text-muted);margin-bottom:2px;letter-spacing:.3px}
.stat-value{font-size:18px;font-weight:600;color:var(--text-strong)}
.stat-sub{font-size:12px;color:var(--text-dim);margin-top:2px}
/* ─── Direction toggle ─── */
.dir-group{display:flex;background:var(--bg-inset);border:1px solid var(--border);border-radius:6px;overflow:hidden}
.dir-btn{padding:8px 16px;font-size:13px;border:none;background:transparent;color:var(--text-muted);cursor:pointer;font-family:inherit;transition:all .2s}
.dir-btn.active{background:var(--accent-solid);color:#fff}
.dir-btn:not(.active):hover{color:var(--text)}
.dir-btn:first-child{border-right:1px solid var(--border)}
#syncBtn{margin-top:0}
.hidden{display:none}
input[type="checkbox"]{accent-color:var(--accent);cursor:pointer}
/* ─── Tabs ─── */
.tabs{display:flex;gap:4px;margin-bottom:16px;border-bottom:1px solid var(--border);flex-wrap:wrap}
.tab-btn{padding:8px 18px;font-size:13px;border:none;background:transparent;color:var(--text-muted);cursor:pointer;font-family:inherit;border-bottom:2px solid transparent;transition:all .2s}
.tab-btn:hover{color:var(--text)}
.tab-btn.active{color:var(--text-strong);border-bottom-color:var(--accent)}
.tab-panel{display:none}
.tab-panel.active{display:block}
/* ─── Thumbnail ─── */
.thumb-wrap{width:var(--thumb-size,48px);height:var(--thumb-size,48px);flex-shrink:0}
.thumb{width:var(--thumb-size,48px);height:var(--thumb-size,48px);object-fit:cover;border-radius:4px;display:block;background:var(--bg)}
/* ─── Preview panel ─── */
.preview-panel{display:none;position:fixed;z-index:1000;background:var(--bg-card);border:1px solid var(--border);border-radius:8px;box-shadow:0 8px 32px var(--shadow);overflow:hidden;pointer-events:none;max-width:420px}
.preview-panel.active{display:block;animation:previewFadeIn .15s ease-out}
.preview-panel img{display:block;max-width:400px;max-height:480px;object-fit:contain}
.preview-panel .preview-name{padding:8px 12px;font-size:12px;color:var(--text-muted);border-top:1px solid var(--border);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
/* ─── Animations ─── */
@keyframes fadeIn{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:translateY(0)}}
@keyframes previewFadeIn{from{opacity:0}to{opacity:1}}
@keyframes slideDown{from{opacity:0;transform:translateY(-10px)}to{opacity:1;transform:translateY(0)}}
.fade-in{animation:fadeIn .35s ease-out both}
#syncBtn.slide-in{animation:slideDown .3s ease-out}
tr.row-enter{animation:fadeIn .35s ease-out both}
/* ─── Help tooltips ─── */
.help-toggle{display:inline-flex;align-items:center;justify-content:center;width:18px;height:18px;border-radius:50%;background:var(--border);color:var(--text-muted);font-size:11px;cursor:pointer;margin-left:4px;transition:all .2s;vertical-align:middle;line-height:18px;font-style:normal;font-weight:600}
.help-toggle:hover{background:var(--accent-solid);color:#fff}
.help-text{font-size:12px;color:var(--text-muted);background:var(--bg);border:1px solid var(--border);border-radius:6px;padding:8px 12px;margin-top:4px;line-height:1.7}
.help-text code{background:var(--bg-inset);padding:1px 5px;border-radius:3px;font-size:11px;color:var(--text)}
.help-text ol{margin:4px 0 0 18px;padding:0}
.help-text li{margin-bottom:3px}
.help-text a{color:var(--accent)}
.pixiv-status{font-size:13px;color:var(--text-muted);margin-left:12px;transition:color .2s}
.pixiv-status.loading{color:var(--accent)}
.pixiv-status.success{color:var(--ok)}
.pixiv-status.error{color:var(--err)}
.pixiv-stats{display:flex;gap:16px;padding:10px 14px;background:var(--bg);border:1px solid var(--border);border-radius:6px;font-size:13px;color:var(--text-muted);flex-wrap:wrap;margin-top:12px}
.pixiv-stats strong{color:var(--text-strong);font-weight:600}
/* ─── Log panel ─── */
.log-box{background:var(--bg);border:1px solid var(--border);border-radius:6px;height:480px;overflow-y:auto;padding:10px 12px;font-family:'SFMono-Regular',Consolas,monospace;font-size:12px;line-height:1.6}
.log-line{display:block;white-space:pre-wrap;word-break:break-all}
.log-line .cat-SCAN{color:var(--cyan)}
.log-line .cat-HASH{color:var(--warn)}
.log-line .cat-SYNC{color:var(--accent)}
.log-line .cat-IMAGE{color:var(--text-muted)}
.log-line .cat-DONE{color:var(--ok)}
.log-line .cat-ERROR{color:var(--err)}
.log-line .cat-INFO{color:var(--text)}
.log-line .cat-BLACKLIST{color:var(--violet)}
</style>
</head>
<body>
<div class="container">

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
      <button class="btn btn-danger hidden" id="syncBtn" disabled>同步到设备A（0 个文件）</button>
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
          <li>打开 <a href="https://www.pixiv.net" target="_blank">pixiv.net</a> 并登录</li>
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
      <input type="password" id="pixivPhpsessid" placeholder="已保存的凭证已隐藏，留空则使用已保存凭证（清空请手动编辑 config.ini）">
      <div id="helpPhpsessid" class="help-text hidden">
        <strong>如何获取 PHPSESSID：</strong>
        <ol>
          <li>在浏览器打开 <a href="https://www.pixiv.net" target="_blank">pixiv.net</a> 并登录账号</li>
          <li>按 <code>F12</code> 打开开发者工具</li>
          <li>切换到 <code>Application</code> 标签 → 左侧 <code>Cookies</code> → <code>https://www.pixiv.net</code></li>
          <li>找到 <code>PHPSESSID</code> 这一行，复制其值（一串字母数字）</li>
        </ol>
        <div style="margin-top:6px;color:var(--err);font-size:11px">⚠ PHPSESSID 相当于你的登录凭证，不会上传到任何第三方服务器</div>
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
        <span>缺失作品: <strong id="pixivMissing">0</strong></span>
        <span>缺失分p总数: <strong id="pixivMissingPages">0</strong></span>
      </div>
      <div class="table-wrap" style="margin-top:12px">
        <table>
          <thead>
            <tr>
              <th style="width:40px">#</th>
              <th>范围</th>
              <th style="width:60px">操作</th>
              <th style="width:100px">ID</th>
              <th style="width:110px">分p</th>
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
      <div class="settings-grid">
      <div class="input-group">
        <label for="settingTheme">界面主题</label>
        <select id="settingTheme">
          <option value="0">深色（默认）</option>
          <option value="1">浅色</option>
        </select>
      </div>
      <div class="input-group">
        <label for="settingThumbSize">缩略图尺寸</label>
        <select id="settingThumbSize">
          <option value="16">特小（16px）</option>
          <option value="24">小（24px）</option>
          <option value="48">标准（48px）</option>
          <option value="64">大（64px）</option>
          <option value="96">特大（96px）</option>
        </select>
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
        <label for="settingMaxRows">结果表行数上限</label>
        <input type="number" id="settingMaxRows" min="10" max="5000" step="10">
        <div class="input-hint">设备同步扫描结果与 Pixiv 查重结果两张结果表的行数上限，与日志、缩略图无关</div>
      </div>
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
      <div id="logList" class="log-box"></div>
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
  };
  const _p = document.getElementById('pixivPhpsessid').value.trim();
  if (_p) data.PHPSESSID = _p;
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
        const rect = this.getBoundingClientRect();
        previewName.textContent = f.name + (f.size != null ? ' (' + formatSize(f.size) + ')' : '');
        const url = '/api/image?url=' + encodeURIComponent(srcUrl) + '&file=' + encodeURIComponent(f.name);
        const seq = ++previewSeq;
        // 图片加载完成才显示面板(防未就绪空框), 再定位
        const show = function() {
          if (seq !== previewSeq) return;   // 迟到的加载: 已换行/已离开, 丢弃
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
const CATS = ['SCAN', 'HASH', 'SYNC', 'IMAGE', 'DONE', 'ERROR', 'BLACKLIST'];

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
}

// 缩略图/主题下拉: change 即联动生效, 持久化由下方统一 blur/change 绑定完成
settingThumbSize.addEventListener('change', function() {
  document.documentElement.style.setProperty('--thumb-size', this.value + 'px');
});
settingTheme.addEventListener('change', function() {
  applyTheme(this.value === '1');
});
[settingThumbSize, settingTheme, settingPreviewDelay, settingPixivInterval, settingMaxRows].forEach(el => {
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
</script>
</body>
</html>"""


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
#   2) 前端: 在 HTML 加控件/面板（或按 TABS 注册表新增标签页）
#   3) 验证: 参考 .omo/evidence/pixiv-web-upgrade/ 各 task 的 QA 模式写 curl/Playwright 验收

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
            if not save_config(data):
                # 文件损坏拒绝覆盖(防凭证被默认值抹除) / 写盘失败
                self._send_json({'error': '配置未保存：config.ini 损坏或写入失败，见服务端日志'})
                return
            self._send_json({'ok': True})
        except Exception as e:
            console_log('ERROR', f'配置保存失败: {e}')
            self._send_json({'error': f'保存失败: {e}'})

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
