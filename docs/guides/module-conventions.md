# docs/guides/module-conventions.md — 单文件模块约定与结构地图

`server.py` 是单文件应用（约 2570 行）：HTTP 服务、业务逻辑、前端 HTML/CSS/JS 全部在一个文件里。本文档是**代码内部结构地图** + 模块组织约定，说明每个行区放什么、新增代码该放哪里、按什么风格写。

> 目标读者：AI。
> 行号为编写时快照，定位源码请以符号名为准。**本表随代码维护——AI 改动代码后必须同步更新对应行区**（AGENTS.md §3.9 文档义务）。

## 1. 结构地图（自上而下）

| 行区 | 内容 | 新增代码放哪 |
|---|---|---|
| 1-24 | 导入（纯标准库） | 新 import 加到这里（**仅标准库**） |
| 25-26 | `PORT=13826`、`IMAGE_EXTS` | 模块级常量加在附近 |
| 28-189 | **配置系统**：目录降级 `_prepare_config_dir`(40) → 注册表 `_CONFIG_KEYS`(78) → 解析钳制 `_parse_config_value`(88) → `load_config`(139)/`save_config`(148)，后者原子写(.tmp+os.replace)、文件损坏时拒绝覆盖保存；解析兜住语法损坏/BOM/坏编码/溢出值 | **不要在这里塞业务逻辑** |
| 190-245 | `console_log`(222)：stderr 彩色输出 + 内存环形缓冲（网页轮询用） | 日志相关工具函数 |
| 247-1603 | **内嵌前端**：`HTML` 常量（整个网页 UI，含 CSS/JS）；改动后的视觉验证见本文档 §6 | 前端改动只在这一区域 |
| 1645-1789 | 数据源：`ftp_list`(1645)/`ftp_download`(1686)/`ftp_upload`(1702)/`local_list`(1766) | 新的数据源读取函数 |
| 1791+ | 本地路径净化：`_safe_error_text`(1791)/`_sanitize_rel_path`(1798)/`_declared_local_bases`(1814)/`_check_local_base`(1824)/`_check_realpath_within`(1833)，防目录穿越 | 路径安全相关 |
| 1973+ | `fetch_all_pixiv_bookmark_ids`：Pixiv 收藏拉取（分页/黑名单/限量/可终止） | Pixiv 相关逻辑 |
| 2089-2222 | **Pixiv 后台 Job 引擎（单槽）**：`pixiv_job` 状态字典(2089) → `run_pixiv_job`(2113) 状态机 `fetching→scanning→matching→done/stopped/error` → `_start_pixiv_job`(2208) 原子启动。关键时序：**每个昂贵阶段前先检查 `stop`** | 新的后台任务引擎放这类区域 |
| 2226-2610 | **HTTP 层** `SyncHandler(BaseHTTPRequestHandler)`：`_send_json`(2232)/`_send_html`(2241)/`_send_error`(2249)/`_check_origin`(2257)/`do_OPTIONS`(2277)/`do_GET`(2285)/`do_POST`(2314) + 各 `_handle_*` 处理器 | 新 API handler 加在这里 |
| 2613+ | `ThreadedServer`：多线程 HTTP 服务器 + `__main__` 启动（自动开浏览器） | 启动逻辑 |

## 2. 关键约定

- 新增 API 端点：在 `do_GET`(2285) 或 `do_POST`(2314) 加 elif 分支 → 写 `_handle_*` 方法 → 更新 `docs/api.md`。
- 新增配置：在 `_CONFIG_KEYS`(78) 注册（若需范围/类型）→ `load_config`/`save_config` 自动覆盖（数值键）→ 前端表单同步 → 更新 `docs/settings.md`。
- 请求体为 JSON 时：读 `Content-Length` → `self.rfile.read` → `json.loads`，参考 `_handle_pixiv_bookmarks`(2418)。
- 所有 API 响应 JSON 用 `ensure_ascii=False`，中文直接输出。

## 3. 风格约定

- **中文注释 + 分区分隔线**：逻辑块之间用 `# ─── 分区名 ───` 分隔（如 `server.py:181` 的 `# ─── Embedded HTML ───`）。
- **代码标识符用英文**（`_handle_ping`、`local_list`），注释/日志/UI 文案用中文。
- **函数职责单一**：一个函数干一件事；超过约 80 行的函数考虑拆分（参照 `run_pixiv_job` 的状态机分段结构）。
- **异常处理**：捕获后必须 `console_log('ERROR', ...)` 记录；错误文本回传前端用 `_safe_error_text` 净化，不裸抛裸传。
- **响应辅助**：HTTP handler 一律用 `_send_json`/`_send_html`/`_send_error`（`server.py:2232`/`2241`/`2249`），不要手写 `send_response` 序列。

## 4. 前后端边界

- 前端完全内嵌在 `HTML` 常量（`server.py:183+`），**没有独立 HTML/CSS/JS 文件**。改 UI = 改这个字符串。
- 前后端交互只走 `/api/*` 端点（见 `docs/api.md`）；同源页面受 `_check_origin` 保护，无跨域问题。
- 前端给后端传参：GET 用 query string，POST 用 JSON body（`Content-Length` + `rfile.read` + `json.loads`，见 `_handle_pixiv_bookmarks`，`server.py:2353`）。

## 5. 后台任务约定（单槽引擎）

需要后台任务时，**复制而不是重写**现有 Pixiv Job 引擎模式（`server.py:2089-2222`）：
- 状态字典 + `stop` 事件 + `lock`（参考 `pixiv_job`，`server.py:2089`）。
- 状态机每个昂贵阶段前**先检查 `stop`**（时序不可颠倒，见 `run_pixiv_job` 注释）。
- 原子启动 check-and-set（`_start_pixiv_job`，`server.py:2208`），并发启动返回"已有任务在运行"。
- 状态/结果拆分两个端点暴露（`/api/pixiv/job` vs `/api/pixiv/job/result`）。


## 6. 验证纪律

- 每次改动后：`python -m py_compile server.py`（必做）。
- 涉及 API：启动服务 curl 冒烟（正例 + 跨源 403 负例）。
- 涉及前端：启动服务后，用 Playwright 驱动页面到目标状态（填表单/切换标签页/触发交互），截图保存；需要精确断言（如颜色）时用 `browser_evaluate` + `getComputedStyle` 比对；需要整体观感判断时，将截图交 multimodal-looker 解读。
- 项目无自动化测试框架，验证靠上述手动循环；不要假装有测试通过。
- **改动代码后同步本表**：新增/移动函数时更新 §1 结构地图对应行区（AGENTS.md §3.9 文档义务）。

## 7. 检查清单

- [ ] 新增代码落在对应分区（见 §1 表格），未在配置系统区塞业务逻辑
- [ ] 仅使用标准库；新 import 已加进导入区
- [ ] 风格一致：中文注释、`# ─── 分区 ───` 分隔、英文标识符
- [ ] 异常处理完整：`console_log('ERROR')` + `_safe_error_text` 净化
- [ ] 后台任务复用单槽引擎模式，stop 检查时序正确
- [ ] `python -m py_compile server.py` 通过
- [ ] 相关 `docs/` 文档已同步（`api.md`/`settings.md`/本文档）

---

> English: [below](#english).

# English

`server.py` is a single-file app (~2570 lines): HTTP server, business logic, and the frontend HTML/CSS/JS all live in one file. This document is the **internal structure map** + module conventions: what each region holds, where new code goes, and how to write it.

> Line numbers are a snapshot — locate source by symbol name. **This map is maintained with the code**: after changing code, sync the affected region in §1 (doc obligation, AGENTS.md §3.9).

## 1. Structure map (top-down)

| Region | Content | Where new code goes |
|---|---|---|
| 1-24 | Imports (stdlib only) | New imports go here (stdlib only) |
| 25-26 | `PORT=13826`, `IMAGE_EXTS` | Module-level constants |
| 28-189 | **Config system**: `_CONFIG_KEYS` registry(78) → `_parse_config_value`(88) → `load_config`(139)/`save_config`(148). Corrupt config falls back to defaults, never raises | **No business logic here** |
| 190-245 | `console_log`(222): file + stderr + ring buffer (web polling) | Logging utilities |
| 247-1603 | **Embedded frontend**: `HTML` constant (entire UI, CSS/JS, ); visual verification after changes: see §6 | All frontend changes |
| 1645-1789 | Data sources: `ftp_list`(1645)/`ftp_download`(1686)/`ftp_upload`(1702)/`local_list`(1766) | New data-source readers |
| 1791+ | Local-path sanitization: `_safe_error_text`(1791)/`_sanitize_rel_path`(1798)/`_declared_local_bases`(1814)/`_check_local_base`(1824)/`_check_realpath_within`(1833), traversal guard | Path-safety code |
| 1973+ | `fetch_all_pixiv_bookmark_ids`: Pixiv bookmark fetching (paging/blacklist/limit/stoppable) | Pixiv logic |
| 2089-2222 | **Pixiv Job engine (single-slot)**: `pixiv_job` state dict(2089) → `run_pixiv_job`(2113) state machine `fetching→scanning→matching→done/stopped/error` → `_start_pixiv_job`(2208) atomic start. Key timing: **check `stop` before every expensive phase** | New background-task engines |
| 2226-2610 | **HTTP layer** `SyncHandler(BaseHTTPRequestHandler)`: `_send_json`(2232)/`_send_html`(2241)/`_send_error`(2249)/`_check_origin`(2257)/`do_OPTIONS`(2277)/`do_GET`(2285)/`do_POST`(2314) + `_handle_*` handlers | New API handlers |
| 2613+ | `ThreadedServer`: threaded HTTP server + `__main__` startup (auto-opens browser) | Startup logic |

## 2. Key conventions

- New API endpoint: add elif branch in `do_GET`(2285) or `do_POST`(2314) → write `_handle_*` method → update `docs/api.md`.
- New setting: register in `_CONFIG_KEYS`(78) (if range/type needed) → `load_config`/`save_config` auto-cover (numeric keys) → sync frontend form → update `docs/settings.md`.
- JSON request bodies: read `Content-Length` → `self.rfile.read` → `json.loads`, see `_handle_pixiv_bookmarks`(2418).
- All API JSON responses use `ensure_ascii=False`; Chinese output directly.

## 3. Style

- Chinese comments + `# ─── section ───` separators between logic blocks (e.g. `server.py:181`).
- English identifiers, Chinese comments/logs/UI text.
- Single-responsibility functions; split functions above ~80 lines (see `run_pixiv_job`'s state-machine sections).
- Exceptions: always `console_log('ERROR', ...)`; sanitize text sent to the frontend via `_safe_error_text`.
- Handlers use `_send_json`/`_send_html`/`_send_error` (2232/2241/2249) — never hand-roll `send_response`.

## 4. Frontend/backend boundary

- Frontend is entirely inside the `HTML` constant (`server.py:183+`); no standalone HTML/CSS/JS files.
- Frontend ↔ backend only via `/api/*` (see `docs/api.md`); same-origin pages are protected by `_check_origin`.
- Params: query string for GET, JSON body for POST (`Content-Length` + `rfile.read` + `json.loads`, see `_handle_pixiv_bookmarks`, 2231).

## 5. Background tasks (single-slot engine)

**Copy, don't rewrite**, the Pixiv Job engine pattern (`server.py:2089-2222`): state dict + `stop` event + `lock` (2089); check `stop` before every expensive phase (order matters, see `run_pixiv_job` comments); atomic check-and-set start (2109) rejecting concurrent runs; split status vs result endpoints.

## 6. Verification discipline

- After every change: `python -m py_compile server.py` (mandatory).
- API changes: curl smoke (positive + cross-origin 403 negative).
- Frontend changes: after starting the service, drive the page to the target state with Playwright (fill forms / switch tabs / trigger interactions) and save screenshots; for precise assertions (e.g. colors) use `browser_evaluate` + `getComputedStyle`; for overall visual judgment, hand the screenshots to multimodal-looker.
- No automated test framework exists; verification is this manual loop. Don't pretend tests pass.
- **Sync this map after code changes**: update the affected region in §1 when functions are added/moved (doc obligation, AGENTS.md §3.9).

## 7. Checklist

- [ ] Code landed in the right region (§1); no business logic inside the config section
- [ ] Stdlib only; new imports added to the import block
- [ ] Style consistent: Chinese comments, `# ─── section ───` separators, English identifiers
- [ ] Exception handling complete: `console_log('ERROR')` + `_safe_error_text`
- [ ] Background tasks reuse the single-slot engine pattern with correct stop timing
- [ ] `python -m py_compile server.py` passes
- [ ] Related `docs/` updated (`api.md`/`settings.md`/this file)
- [ ] §1 structure map synced with the current code
