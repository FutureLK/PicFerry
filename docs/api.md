# docs/api.md — API 端点契约

`server.py` HTTP 服务的全部端点。所有 `/api/*` 请求必须先通过 `_check_origin`（`server.py:2158`）同源校验，否则返回 403。

> 目标读者：人类 + AI。AI 新增端点时请走 `docs/guides/adding-an-api.md` 的流程，并同步更新本文档。
> 行号为编写时快照，定位源码请以符号名为准。

## 通用约定

- 基址：`http://<host>:13826`（端口硬约束，见 `AGENTS.md` §3.7）
- 响应 JSON 一律 `ensure_ascii=False`（`_send_json`，`server.py:1982`），中文直接输出
- 错误响应统一 `{"error": "..."}`，错误文本经 `_safe_error_text` 净化
- 非 `/api/` 路径（`/`）返回网页；未知路径返回 404

## 端点总览

| 端点 | 方法 | 参数 | 说明 | 处理函数 |
|---|---|---|---|---|
| `/` | GET | — | 返回内嵌网页（`HTML` 常量） | `_send_html`(1991) |
| `/api/list` | GET | `url` | 扫描设备文件列表（HTTP/FTP/本地） | `_handle_list`(2095) |
| `/api/hash` | POST | `url`, `file` | 计算远程文件 SHA256 | `_handle_hash`(2119) |
| `/api/copy` | POST | `from`, `to`, `file` | 同步单个文件（来源→目标） | `_handle_copy`(2134) |
| `/api/image` | GET | `url`, `file` | 图片代理（转发远程图片） | `_handle_image` |
| `/api/log` | GET/POST | `cat`, `msg` | 前端日志推送到终端+文件+内存缓冲 | `_handle_log` |
| `/api/logs` | GET | `since` | 增量拉取日志（环形缓冲） | `_handle_logs` |
| `/api/logs/clear` | POST | — | 清空内存日志缓冲 | `_handle_logs_clear` |
| `/api/config` | GET | — | 读取配置（PHPSESSID 不回显） | `_handle_config` |
| `/api/config/save` | POST | 全部配置字段 | 保存配置到 `config.ini` | `_handle_config_save`(2498) |
| `/api/pixiv/bookmarks` | POST | `uid`, `phpsessid`, `path`, `limit?` | 启动 Pixiv 收藏查重（后台 Job） | `_handle_pixiv_bookmarks`(2168) |
| `/api/pixiv/bookmarks/stop` | POST | — | 请求终止当前 Job（仅限本机调用，远程返回 error） | `_handle_pixiv_stop`(2205) |
| `/api/pixiv/job` | GET | — | 轮询 Job 状态（不含 result） | `_handle_pixiv_job`(2210) |
| `/api/pixiv/job/result` | GET | — | 取终态结果（done 后含 matched） | `_handle_pixiv_job_result`(2219) |
| `/api/blacklist` | GET | — | 读取黑名单 ID 列表 | `_handle_blacklist`(2225) |
| `/api/blacklist/add` | POST | `id` | 添加黑名单（裸 ID 或作品链接） | `_handle_blacklist_add`(2229) |
| `/api/blacklist/remove` | POST | `id` | 移除黑名单 | `_handle_blacklist_remove` |
| `/api/blacklist/clear` | POST | — | 清空黑名单 | `_handle_blacklist_clear` |

## 端点详情

### GET `/api/list`

扫描设备图片列表。`url` 支持：
- HTTP 目录列表 URL → `http_fetch` + `parse_html_listing`
- FTP 地址（`is_ftp`）→ `ftp_list`(1395)，按 `IMAGE_EXTS` 过滤
- 本地路径（`is_local_path`）→ `local_list`(1516)

**响应**：`{"files": [{"name": "...", "size": N}, ...], "total": N}`
**错误**：`{"error": "...", "files": []}`
**声明门**：`url` 为本地路径形态时仅接受已声明基座——未声明返回 `{"error": "未声明的本地路径", "files": []}`；`http://`、`ftp://` 网络地址不受此限。

### POST `/api/hash`

**请求**：`url`（远程位置）、`file`（相对路径）
**响应**：`{"filename": "...", "sha256": "<hex>"}`

### POST `/api/copy`

**请求**：`from`（来源位置）、`to`（目标位置）、`file`（相对路径）
**逻辑**：`_sanitize_rel_path` 净化路径 → 读源 → 按目标类型写（本地/`_check_local_base`+`_check_realpath_within` 校验；FTP/`ftp_upload`；HTTP/`http_put`）
**响应**：`{"success": true, "filename": "..."}` 或 `{"success": false, "error": "..."}`

### GET `/api/config`

**响应**：全部配置字段 + `hasPhpsessid`（布尔）。**绝不包含 PHPSESSID 明文。**

### POST `/api/config/save`

**请求体**：JSON，字段见 `docs/settings.md`。空值语义：PHPSESSID 留空保留原值；其余留空回落默认。
**声明权**：非本机（非回环）来源提交时剥除本机专属键——`dev1ceA/dev1ceB/PixivL` 的本地盘形态值与空串、`PHPSESSID` 全值；网络地址形态不受限。剥除动作记 INFO 日志，其余键照常保存。
**响应**：`{"ok": true}`；失败为 `{"error": "..."}`——写入采用原子替换（.tmp + os.replace），若 `config.ini` 已损坏则拒绝覆盖保存（防 PHPSESSID 被空默认值抹除）或写盘失败（参考 `_handle_config_save`，`server.py:2498`）

### POST `/api/pixiv/bookmarks`

> 上游接口来源：Pixiv Web AJAX 接口（非官方文档 `github.com/daydreamer-json/pixiv-ajax-api-docs`「Get user bookmarks」），字段语义（pageCount）经 `pixiv-api.readthedocs.io` 核实；代码见 `server.py:1653 PIXIV_BOOKMARK_URL`。

**请求体**：JSON `{"uid": "...", "phpsessid": "...", "path": "...", "limit": N?}`（limit 缺省用配置 `pixivLimit`；`allowLan=0` 时 phpsessid 缺省回落到配置存储值；`path` 为本地路径形态时同样须为已声明基座，否则 Job 落入 error 态"未声明的本地路径"）
**逻辑**：校验 → `_start_pixiv_job`(1958) 原子启动单槽任务 → 立即返回
**响应**：`{"ok": true, "status": "fetching"}` 或 `{"error": "..."}`（如"已有任务在运行"）

### GET `/api/pixiv/job`

Job 状态机：`idle | fetching | scanning | matching | done | stopped | error`（`run_pixiv_job`，`server.py:1863`）。
**响应**：`{"status": "...", "progress": {"phase", "fetched", "total"}, "error": null|str, "summary": null|{total_bookmarks, local_count, missing_works, missing_pages}}`——其中 `error` 文本经脱敏与截断（≤120 字符），不含本地路径等敏感细节

### GET `/api/pixiv/job/result`

**响应**：`{"matched": [{"illust_id", "pageCount", "saved_pages", "missing_pages", "range"}, ...]}`；非 done 状态返回空数组。

### GET/POST `/api/blacklist*`

- `GET /api/blacklist` → `{"ids": [排序后的 ID 列表]}`
- `POST /api/blacklist/add`，请求体 `{"id": "裸ID或/artworks/链接"}` → `{"ok": true}`
- `POST /api/blacklist/remove`，请求体 `{"id": "..."}` → `{"ok": true}`
- `POST /api/blacklist/clear` → `{"ok": true}`

### GET/POST `/api/log*`

- `GET /api/logs?since=<id>` → 增量日志，`truncated` 标志表示需重载
- `POST /api/logs/clear` → 清内存缓冲
- `POST /api/log`（body 或 query `cat`/`msg`）→ 前端日志转发，经 `console_log`(156)；`msg` 截断至 512 字符、`cat` 至 32 字符后入库；`msg` 截断至 512 字符、`cat` 至 32 字符后入库

## 安全

- **同源闸门**：`_check_origin`（`server.py:2158`）校验 Origin/Referer 与 Host 一致；`allowLan=0` 时额外校验 Host ∈ `{127.0.0.1, localhost, ::1}`（防 DNS rebinding）。所有 `/api/*`（含 OPTIONS 预检）必须经过，新端点不得绕过。
- **路径净化**：`/api/copy` 写本地时经 `_sanitize_rel_path` + `_check_local_base` + `_check_realpath_within` 防目录穿越；未声明的本地基址读写被拒（`_declared_local_bases`，`server.py:1564`）。
- **扫描声明门**：目录列表（`/api/list`）与 Pixiv 本地扫描同受基座校验（`_assert_declared_scan_base`），未声明的本地目录不可枚举，与读链路同口径。
- **声明权边界**：本地盘形态的设备键、其空串清除意图及 `PHPSESSID` 仅回环来源可经 `/api/config/save` 写入（`strip_remote_locked_keys`），远程设备保留网络地址形态的正常设置能力。
- **PHPSESSID**：任何端点不回显明文。

---

> English: [below](#english).

# English

Contract for every `/api/*` endpoint. All `/api/*` requests must pass the same-origin check `_check_origin` (`server.py:2158`) first, or get a 403.

## Conventions

- Base: `http://<host>:13826` (port is a hard constraint, see `AGENTS.md` §3.7)
- All JSON responses use `ensure_ascii=False` (`_send_json`, `server.py:1982`); Chinese output directly
- Errors: `{"error": "..."}` with sanitized text via `_safe_error_text`
- Non-`/api/` path `/` serves the embedded page; unknown paths return 404

## Endpoints

| Endpoint | Method | Params | Purpose | Handler |
|---|---|---|---|---|
| `/` | GET | — | Embedded web UI (`HTML` constant) | `_send_html`(1991) |
| `/api/list` | GET | `url` | List device image files (HTTP/FTP/local) | `_handle_list`(2095) |
| `/api/hash` | POST | `url`, `file` | SHA256 of a remote file | `_handle_hash`(2119) |
| `/api/copy` | POST | `from`, `to`, `file` | Sync one file (source→target) | `_handle_copy`(2134) |
| `/api/image` | GET | `url`, `file` | Image proxy | `_handle_image` |
| `/api/log` | GET/POST | `cat`, `msg` | Forward frontend logs | `_handle_log` |
| `/api/logs` | GET | `since` | Incremental log polling (ring buffer) | `_handle_logs` |
| `/api/logs/clear` | POST | — | Clear in-memory log buffer | `_handle_logs_clear` |
| `/api/config` | GET | — | Read config (PHPSESSID never echoed) | `_handle_config` |
| `/api/config/save` | POST | all fields | Save config to `config.ini` | `_handle_config_save`(2498) |
| `/api/pixiv/bookmarks` | POST | `uid`, `phpsessid`, `path`, `limit?` | Start Pixiv dedup job (background) | `_handle_pixiv_bookmarks`(2168) |
| `/api/pixiv/bookmarks/stop` | POST | — | Request job stop (loopback clients only; remote gets error) | `_handle_pixiv_stop`(2205) |
| `/api/pixiv/job` | GET | — | Poll job status (no result; error field sanitized+truncated) | `_handle_pixiv_job`(2210) |
| `/api/pixiv/job/result` | GET | — | Final result (matched on done) | `_handle_pixiv_job_result`(2219) |
| `/api/blacklist` | GET | — | Read blacklist IDs | `_handle_blacklist`(2225) |
| `/api/blacklist/add` | POST | `id` | Add blacklist entry (ID or artwork link) | `_handle_blacklist_add`(2229) |
| `/api/blacklist/remove` | POST | `id` | Remove blacklist entry | `_handle_blacklist_remove` |
| `/api/blacklist/clear` | POST | — | Clear blacklist | `_handle_blacklist_clear` |

## Security

- **Same-origin gate**: `_check_origin` (`server.py:2158`) — Origin/Referer must match Host; with `allowLan=0` Host must be in `{127.0.0.1, localhost, ::1}` (DNS-rebinding guard). Every `/api/*` request (including OPTIONS) must pass it; new endpoints must not bypass it.
- **Path sanitization**: local writes in `/api/copy` go through `_sanitize_rel_path` + `_check_local_base` + `_check_realpath_within` (directory-traversal guard); undeclared local bases are rejected (`_declared_local_bases`, `server.py:1564`).
- **Declared-base scan gate**: directory listing (`/api/list`) and Pixiv local scans go through the same base check (`_assert_declared_scan_base`); undeclared local directories cannot be enumerated — same policy as the read path.
- **Declaration authority**: local-form device keys, their empty-string clears, and `PHPSESSID` are only writable via `/api/config/save` from loopback clients (`strip_remote_locked_keys`); remote devices keep normal network-address configuration.
- **PHPSESSID**: never echoed by any endpoint.
