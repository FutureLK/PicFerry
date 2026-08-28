# docs/guides/module-conventions.md — 模块约定与结构地图

`server.py`（约 132 行）是服务端主文件：导入装配 + 服务启动；HTTP 路由层已拆到 `handler.py`（`SyncHandler`，约 457 行）。前端 HTML/CSS/JS 已拆分为 `static/` 真实文件（index.html / style.css / app.js），由 `webassets.py` 在导入期装配回完整 `HTML`；日志/配置/路径安全/数据源/Pixiv 引擎外移到同目录一方模块（logging_util.py / config_store.py / pathsafety.py / datasources.py / pixiv.py / handler.py）。本文档是**代码内部结构地图** + 模块组织约定，说明每个行区放什么、新增代码该放哪里、按什么风格写。

> 目标读者：AI。
> 行号为编写时快照，定位源码请以符号名为准。**本表随代码维护——AI 改动代码后必须同步更新对应行区**（AGENTS.md §3.9 文档义务）。

## 1. 结构地图（自上而下）

| 行区 | 内容 | 新增代码放哪 |
|---|---|---|
| 20-41 | 导入：纯标准库(1-19) + 一方模块 from-import（logging_util / config_store / pathsafety / datasources / **webassets** / pixiv / handler），导入期逐模块 `perf_counter` 计时写入 `logging_util.IMPORT_TIMING`（debug 诊断数据源） | 新 import 加到这里（**仅标准库 + 一方模块**） |
| 27 | `PORT=13826`（`IMAGE_EXTS` 已外移 datasources.py） | 模块级常量加在附近 |
| 30-50 | **声明权控制**：`strip_remote_locked_keys`(35)——远程写配置时剥除本地盘声明与 PHPSESSID | 同类安全逻辑 |
| 52-53 | **前端装配分区**：`HTML` 由 webassets.py 读 `static/` 三件套在导入期拼回（逐字节等价拆分前常量），`_send_html`(117) 下发 | **前端改动改 static/ 对应文件**；装配逻辑改 webassets.py |
| 55-99 | Pixiv API 接口文档注释 + `from pixiv import ...`(99) | Pixiv 接口文档注释 |
| 101-501 | **HTTP 层** `SyncHandler(BaseHTTPRequestHandler)`：`_send_json`(108)/`_send_html`(117)/`_send_error`(125)/`_check_origin`(133)/`do_OPTIONS`(158)/`do_GET`(166)/`do_POST`(195) + 各 `_handle_*` 处理器 | 新 API handler 加在这里 |
| 503-534 | `ThreadedServer`(505)：多线程 HTTP 服务器 + `main`(509)/`__main__` 启动（自动开浏览器） | 启动逻辑 |
| — | **logging_util.py**：`console_log`(43) + `LOG_COLORS`/`RESET`/`_USE_COLOR`(含 Windows ANSI 检测)/`LOG_BUFFER`/`LOG_SEQ`/`LOG_LAST_ID`/`LOG_LOCK`（stderr 彩色输出 + 内存环形缓冲，网页轮询用） | 日志相关改动改 logging_util.py |
| — | **config_store.py**：`_CONFIG_KEYS` 注册表 → `load_config`(121)/`save_config`(130)（原子写 .tmp+os.replace、文件损坏时拒绝覆盖保存）；`runtime_dir`(16) 兼容 EXE（frozen 时取 EXE 所在目录） | 配置读写改动改 config_store.py |
| — | **pathsafety.py**：路径安全三层防线 `_sanitize_rel_path`(39) → `_check_local_base`(71) → `_check_realpath_within`(80)，外加 `_safe_error_text`(32)、`_assert_declared_scan_base`(91) | 路径安全改动改 pathsafety.py |
| — | **datasources.py**：`ftp_list`(54)/`ftp_download`(95)/`ftp_upload`(111)/`local_list`(152)/`http_fetch`(35)/`http_put`(46) 等数据源读取 | 新的数据源读取函数 |
| — | **pixiv.py**：`fetch_all_pixiv_bookmark_ids`(87) 收藏拉取（分页/限量/可终止）+ 单槽 Job 引擎 `pixiv_job`(203)/`run_pixiv_job`(229)/`_start_pixiv_job`(325) + 黑名单读写 `load_blacklist`(27)/`save_blacklist`(50) | Pixiv 逻辑 / 后台任务引擎 |
| — | **webassets.py + static/**：前端三件套 `static/{index.html, style.css, app.js}`——index.html 为骨架，`<style>`/`<script>` 标签保留、块内容位置是 `@@CSS@@`/`@@JS@@` 占位符；`resource_dir()` 兼容 PyInstaller（frozen 取 `sys._MEIPASS`，打包需 `--add-data "static;static"`） | 前端结构 / 装配逻辑改动 |
| — | **handler.py**：`SyncHandler(BaseHTTPRequestHandler)` HTTP 路由层（`_check_origin` / `do_GET` / `do_POST` + 全部 `_handle_*`）+ `strip_remote_locked_keys`（声明权剥除）+ `_emit_import_timing`（debugMode 关→开时补发模块导入耗时，数据只读自 `logging_util.IMPORT_TIMING`） | 新 API handler 加在这里 |

## 2. 关键约定

- 新增 API 端点：在 `do_GET`(166) 或 `do_POST`(195) 加 elif 分支 → 写 `_handle_*` 方法 → 更新 `docs/api.md`。
- 新增配置：在 `_CONFIG_KEYS`（config_store.py）注册（若需范围/类型）→ `load_config`/`save_config` 自动覆盖（数值键）→ 前端表单（static/index.html）同步 → 更新 `docs/settings.md`。
- 请求体为 JSON 时：读 `Content-Length` → `self.rfile.read` → `json.loads`，参考 `_handle_pixiv_bookmarks`(300)。
- 所有 API 响应 JSON 用 `ensure_ascii=False`，中文直接输出。

## 3. 风格约定

- **中文注释 + 分区分隔线**：逻辑块之间用 `# ─── 分区名 ───` 分隔（如 `server.py:30` 的 `# ─── 声明权控制 ───`）。
- **代码标识符用英文**（`_handle_ping`、`local_list`），注释/日志/UI 文案用中文。
- **函数职责单一**：一个函数干一件事；超过约 80 行的函数考虑拆分（参照 pixiv.py `run_pixiv_job` 的状态机分段结构）。
- **异常处理**：捕获后必须 `console_log('ERROR', ...)` 记录；错误文本回传前端用 `_safe_error_text` 净化，不裸抛裸传。
- **响应辅助**：HTTP handler 一律用 `_send_json`/`_send_html`/`_send_error`（`server.py:108`/`117`/`125`），不要手写 `send_response` 序列。

## 4. 前后端边界

- 前端已拆分为真实文件：`static/index.html`（骨架）+ `static/style.css` + `static/app.js`，由 **webassets.py** 在导入期替换占位符装配成完整 `HTML`（`server.py:25` 导入）。**没有内嵌 HTML 字符串**；改 UI = 改 `static/` 对应文件，改装配逻辑 = 改 webassets.py。
- 前后端交互只走 `/api/*` 端点（见 `docs/api.md`）；同源页面受 `_check_origin` 保护，无跨域问题。
- 前端给后端传参：GET 用 query string，POST 用 JSON body（`Content-Length` + `rfile.read` + `json.loads`，见 `_handle_pixiv_bookmarks`，`server.py:300`）。

## 5. 后台任务约定（单槽引擎）

需要后台任务时，**复制而不是重写**现有 Pixiv Job 引擎模式（**pixiv.py**）：
- 状态字典 + `stop` 事件 + `lock`（参考 `pixiv_job`，pixiv.py:203）。
- 状态机每个昂贵阶段前**先检查 `stop`**（时序不可颠倒，见 `run_pixiv_job` 注释）。
- 原子启动 check-and-set（`_start_pixiv_job`，pixiv.py:325），并发启动返回"已有任务在运行"。
- 状态/结果拆分两个端点暴露（`/api/pixiv/job` vs `/api/pixiv/job/result`）。


## 6. 验证纪律

- 每次改动后：`python -m py_compile server.py webassets.py`（必做）。
- 涉及 API：启动服务 curl 冒烟（正例 + 跨源 403 负例）。
- 涉及前端：改 `static/` 后启动服务，用 Playwright 驱动页面到目标状态（填表单/切换标签页/触发交互），截图保存；需要精确断言（如颜色）时用 `browser_evaluate` + `getComputedStyle` 比对；需要整体观感判断时，将截图交 multimodal-looker 解读。
- 项目无自动化测试框架，验证靠上述手动循环；不要假装有测试通过。
- **改动代码后同步本表**：新增/移动函数时更新 §1 结构地图对应行区（AGENTS.md §3.9 文档义务）。

## 7. 检查清单

- [ ] 新增代码落在对应分区（见 §1 表格），未在配置系统区塞业务逻辑
- [ ] 仅使用标准库；新 import 已加进导入区
- [ ] 风格一致：中文注释、`# ─── 分区 ───` 分隔、英文标识符
- [ ] 异常处理完整：`console_log('ERROR')` + `_safe_error_text` 净化
- [ ] 后台任务复用单槽引擎模式，stop 检查时序正确
- [ ] `python -m py_compile server.py webassets.py` 通过
- [ ] 相关 `docs/` 文档已同步（`api.md`/`settings.md`/本文档）

---

> English: [below](#english).

# English

`server.py` (~534 lines) is the main server file: HTTP server and business logic. The frontend HTML/CSS/JS is split into real files under `static/` (index.html / style.css / app.js), assembled back into the full `HTML` string by `webassets.py` at import time. Logging/config/path-safety/datasources/Pixiv engine live in sibling first-party modules (logging_util.py / config_store.py / pathsafety.py / datasources.py / pixiv.py). This document is the **internal structure map** + module conventions: what each region holds, where new code goes, and how to write it.

> Line numbers are a snapshot — locate source by symbol name. **This map is maintained with the code**: after changing code, sync the affected region in §1 (doc obligation, AGENTS.md §3.9).

## 1. Structure map (top-down)

| Region | Content | Where new code goes |
|---|---|---|
| 1-25 | Imports: stdlib(1-19) + first-party from-imports (logging_util / config_store / pathsafety / datasources / **webassets**(25, provides `HTML`)) | New imports go here (stdlib + first-party only) |
| 27 | `PORT=13826` (`IMAGE_EXTS` moved to datasources.py) | Module-level constants |
| 30-50 | **Declaration guard**: `strip_remote_locked_keys`(35) — strips local-disk declarations and PHPSESSID from remote config writes | Similar security logic |
| 52-53 | **Frontend assembly section**: `HTML` is assembled at import time by webassets.py from the `static/` trio (byte-identical to the pre-split constant), served by `_send_html`(117) | **Frontend changes go to static/ files**; assembly logic to webassets.py |
| 55-99 | Pixiv API doc comments + `from pixiv import ...`(99) | Pixiv API doc comments |
| 101-501 | **HTTP layer** `SyncHandler(BaseHTTPRequestHandler)`: `_send_json`(108)/`_send_html`(117)/`_send_error`(125)/`_check_origin`(133)/`do_OPTIONS`(158)/`do_GET`(166)/`do_POST`(195) + `_handle_*` handlers | New API handlers |
| 503-534 | `ThreadedServer`(505): threaded HTTP server + `main`(509)/`__main__` startup (auto-opens browser) | Startup logic |
| — | **logging_util.py**: `console_log`(43) + `LOG_COLORS`/`RESET`/`_USE_COLOR`(incl. Windows ANSI detection)/`LOG_BUFFER`/`LOG_SEQ`/`LOG_LAST_ID`/`LOG_LOCK` (stderr colored output + in-memory ring buffer for web polling) | Logging changes go to logging_util.py |
| — | **config_store.py**: `_CONFIG_KEYS` registry → `load_config`(121)/`save_config`(130) (atomic write, corrupt file never overwritten); `runtime_dir`(16) resolves the EXE dir when frozen | Config changes go to config_store.py |
| — | **pathsafety.py**: three-layer path-safety `_sanitize_rel_path`(39) → `_check_local_base`(71) → `_check_realpath_within`(80), plus `_safe_error_text`(32), `_assert_declared_scan_base`(91) | Path-safety changes go to pathsafety.py |
| — | **datasources.py**: `ftp_list`(54)/`ftp_download`(95)/`ftp_upload`(111)/`local_list`(152)/`http_fetch`(35)/`http_put`(46) and other data-source readers | New data-source readers |
| — | **pixiv.py**: `fetch_all_pixiv_bookmark_ids`(87) bookmark fetching (paging/limit/stoppable) + single-slot Job engine `pixiv_job`(203)/`run_pixiv_job`(229)/`_start_pixiv_job`(325) + blacklist `load_blacklist`(27)/`save_blacklist`(50) | Pixiv logic / background-task engines |
| — | **webassets.py + static/**: frontend trio `static/{index.html, style.css, app.js}` — index.html is the skeleton with `<style>`/`<script>` tags kept and `@@CSS@@`/`@@JS@@` placeholders where the block contents were; `resource_dir()` is PyInstaller-aware (frozen → `sys._MEIPASS`; packaging needs `--add-data "static;static"`) | Frontend structure / assembly changes |

## 2. Key conventions

- New API endpoint: add elif branch in `do_GET`(166) or `do_POST`(195) → write `_handle_*` method → update `docs/api.md`.
- New setting: register in `_CONFIG_KEYS` (config_store.py) (if range/type needed) → `load_config`/`save_config` auto-cover (numeric keys) → sync frontend form (static/index.html) → update `docs/settings.md`.
- JSON request bodies: read `Content-Length` → `self.rfile.read` → `json.loads`, see `_handle_pixiv_bookmarks`(300).
- All API JSON responses use `ensure_ascii=False`; Chinese output directly.

## 3. Style

- Chinese comments + `# ─── section ───` separators between logic blocks (e.g. `server.py:30`).
- English identifiers, Chinese comments/logs/UI text.
- Single-responsibility functions; split functions above ~80 lines (see pixiv.py `run_pixiv_job`'s state-machine sections).
- Exceptions: always `console_log('ERROR', ...)`; sanitize text sent to the frontend via `_safe_error_text`.
- Handlers use `_send_json`/`_send_html`/`_send_error` (108/117/125) — never hand-roll `send_response`.

## 4. Frontend/backend boundary

- The frontend is split into real files: `static/index.html` (skeleton) + `static/style.css` + `static/app.js`, assembled into the full `HTML` by **webassets.py** at import time (imported at `server.py:25`). There is **no embedded HTML string**; UI changes go to the `static/` files, assembly changes to webassets.py.
- Frontend ↔ backend only via `/api/*` (see `docs/api.md`); same-origin pages are protected by `_check_origin`.
- Params: query string for GET, JSON body for POST (`Content-Length` + `rfile.read` + `json.loads`, see `_handle_pixiv_bookmarks`, 300).

## 5. Background tasks (single-slot engine)

**Copy, don't rewrite**, the Pixiv Job engine pattern (**pixiv.py**): state dict + `stop` event + `lock` (`pixiv_job`, pixiv.py:203); check `stop` before every expensive phase (order matters, see `run_pixiv_job` comments); atomic check-and-set start (pixiv.py:325) rejecting concurrent runs; split status vs result endpoints.

## 6. Verification discipline

- After every change: `python -m py_compile server.py webassets.py` (mandatory).
- API changes: curl smoke (positive + cross-origin 403 negative).
- Frontend changes: after editing `static/` and starting the service, drive the page to the target state with Playwright (fill forms / switch tabs / trigger interactions) and save screenshots; for precise assertions (e.g. colors) use `browser_evaluate` + `getComputedStyle`; for overall visual judgment, hand the screenshots to multimodal-looker.
- No automated test framework exists; verification is this manual loop. Don't pretend tests pass.
- **Sync this map after code changes**: update the affected region in §1 when functions are added/moved (doc obligation, AGENTS.md §3.9).

## 7. Checklist

- [ ] Code landed in the right region (§1); no business logic inside the config section
- [ ] Stdlib only; new imports added to the import block
- [ ] Style consistent: Chinese comments, `# ─── section ───` separators, English identifiers
- [ ] Exception handling complete: `console_log('ERROR')` + `_safe_error_text`
- [ ] Background tasks reuse the single-slot engine pattern with correct stop timing
- [ ] `python -m py_compile server.py webassets.py` passes
- [ ] Related `docs/` updated (`api.md`/`settings.md`/this file)
- [ ] §1 structure map synced with the current code
