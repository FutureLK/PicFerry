# docs/guides/adding-an-api.md — 新增 API 端点

给 PicFerry 新增一个 `/api/*` 端点的完整流程。以新增端点 `GET /api/ping` 为例。

> 目标读者：AI。
> 行号为编写时快照，定位源码请以符号名为准。

## 0. 速览：触碰点

```
do_GET (handler.py:175) 或 do_POST (204)   ← 加 elif 分支（必须位于 _check_origin 之后）
   │
   ├─→ 写 _handle_* 方法（SyncHandler 内, handler.py:110+）
   │        │
   │        ├─→ _send_json (117) / _send_error (134) 响应
   │        └─→ console_log (logging_util.py:49) 日志
   │
   ├─→ 前端 JS（static/app.js）调用新端点   ← 如需要
   └─→ docs/api.md 端点总览表 + 详情            ← 必须
```

## 1. 步骤

**步骤 1：确认方法并在路由表加分支。**
- GET 端点 → `do_GET`（`handler.py:175`）加 elif；POST 端点 → `do_POST`（`handler.py:204`）加 elif。
- 注意路由分发前的 `_check_origin` 守卫（`handler.py:179`/`208`）：**所有 `/api/` 请求自动经过它，新端点不需要也不能绕过**。分支本身不需要重复校验。
- 路径匹配用精确相等（`parsed.path == '/api/ping'`）；有查询参数时 `parsed.query` 已由 `parse_qs` 解析进 `params`（`handler.py:177`）。

**步骤 2：写 `_handle_*` 方法。** 在 `SyncHandler` 类内（`handler.py:110` 起）按现有 handler 风格添加：

```python
def _handle_ping(self):
    """GET /api/ping: 健康检查"""
    self._send_json({'pong': True})
```

关键约定：
- **响应用 `_send_json`**（`handler.py:117`，自动 `ensure_ascii=False`）；错误用 `_send_error(code, msg)`（`handler.py:134`）或 JSON `{'error': ...}`。
- **参数读取**：GET 用 `params.get('key', [None])[0]`；POST JSON 体参考 `_handle_pixiv_bookmarks`（`handler.py:309`）：读 `Content-Length` → `self.rfile.read` → `json.loads`，解析失败返回 `{'error': 'Invalid request body: ...'}`。
- **日志**：成功 `console_log('SCAN', ...)`，失败 `console_log('ERROR', ...)`。
- **错误文本**：返回给前端的异常信息用 `_safe_error_text` 净化，不要直接 `str(e)`。

**步骤 3：校验输入。** 缺参时返回 `{'error': 'Missing xxx parameter'}`（参考 `_handle_list`，`handler.py:235`），不要静默用默认值吞掉错误。

**步骤 4：前端调用（如需要）。** 在 `static/app.js` 中 `fetch('/api/ping')`。跨端调用受 `_check_origin` 保护，同源页面无碍。

**步骤 5：更新 `docs/api.md`。** 在端点总览表加一行（端点/方法/参数/说明/处理函数），如需细节再加一节"端点详情"。同步更新方法签名处行号。

**步骤 6：验证。**
- `python -m py_compile server.py handler.py`
- 启动服务后 curl 冒烟：`curl http://127.0.0.1:13826/api/ping` 应返回 `{"pong": true}`。
- 跨源负例：带错误 `Origin` 头请求应返回 403（`_check_origin` 生效）。

## 2. 若端点是后台任务（Pixiv Job 模式）

如果端点要启动一个长时间运行的任务（如扫描、拉取），参考现有 **单槽 Job 引擎**（pixiv.py，`pixiv_job` 从 203 行起）：
- 状态字典 + `threading.Event()` 停止事件 + `threading.Lock()`（`pixiv_job`，`pixiv.py:203`）。
- 状态机阶段切换前**先检查 stop**（`run_pixiv_job`，`pixiv.py:229`），时序约束不可颠倒。
- 启动用原子 check-and-set（`_start_pixiv_job`，`pixiv.py:325`），重复启动返回"已有任务在运行"。
- 提供轻量轮询端点（不含大结果）与终态结果端点两个口（对比 `/api/pixiv/job` 与 `/api/pixiv/job/result`）。

## 3. 检查清单

- [ ] `do_GET`/`do_POST` 已加 elif 分支，位于 `_check_origin` 守卫之后且未绕过它
- [ ] `_handle_*` 方法已写：参数校验、`_send_json` 响应、`console_log` 日志、`_safe_error_text` 净化
- [ ] 缺参/非法体返回明确错误，不静默吞错
- [ ] 路径精确匹配，无歧义前缀冲突（注意 `/api/ping` 与 `/api/ping/xxx` 是不同路径）
- [ ] 前端 JS 已调用（如需要）
- [ ] `docs/api.md` 已更新（总览表 + 详情）
- [ ] `python -m py_compile server.py handler.py` 通过
- [ ] curl 冒烟通过；跨源请求返回 403
- [ ] 未触碰红线：无第三方依赖、无明文 PHPSESSID、未引入未注册配置

## 4. 注意事项

- **不要绕过 `_check_origin`**：它是安全闸门（`AGENTS.md` §3.5），新端点哪怕只服务局域网也要经过。
- **行号漂移**：上述行号是快照，动手前用符号名重新定位。
- **文档同步是义务**：改完 API 不更新 `docs/api.md` = 违反 `AGENTS.md` §3.9。

---

> English: [below](#english).

# English

Full procedure for adding an `/api/*` endpoint. Example: `GET /api/ping`.

## 0. Touch points

```
do_GET (handler.py:175) or do_POST (204)   ← add elif branch (must sit after the _check_origin guard)
   ├─→ write _handle_* method (inside SyncHandler, handler.py:110+)
   │        ├─→ respond via _send_json (117) / _send_error (134)
   │        └─→ log via console_log (logging_util.py:49)
   ├─→ frontend JS (static/app.js) calls the endpoint   ← if needed
   └─→ docs/api.md overview table + details                   ← required
```

## 1. Steps

1. **Route**: add an elif in `do_GET` (handler.py:175) or `do_POST` (204). The `_check_origin` guard (handler.py:179/208) already covers all `/api/*` — do not duplicate or bypass it. Query params come pre-parsed in `params` (handler.py:177).
2. **Handler**: add `_handle_ping` inside `SyncHandler` (handler.py:110+). Use `_send_json` (117); for POST JSON bodies follow `_handle_pixiv_bookmarks` (handler.py:309): read `Content-Length` → `self.rfile.read` → `json.loads`, return `{'error': 'Invalid request body: ...'}` on failure. Log via `console_log`; sanitize exception text with `_safe_error_text`.
3. **Validate input**: return `{'error': 'Missing xxx parameter'}` on missing params (like `_handle_list`, handler.py:235); never swallow errors with silent defaults.
4. **Frontend** (if needed): `fetch('/api/ping')` in `static/app.js`.
5. **Docs**: add a row to `docs/api.md` overview table (+ a details section if warranted).
6. **Verify**: `python -m py_compile server.py handler.py`; curl smoke; cross-origin request with a bad `Origin` must return 403.

## 2. Background-task endpoints (Pixiv Job pattern)

For long-running endpoints, copy the single-slot Job engine (pixiv.py, `pixiv_job` from line 203): state dict + `threading.Event()` stop + `threading.Lock()` (`pixiv_job`, 203); check `stop` before every expensive phase (`run_pixiv_job`, 229); atomic check-and-set start (`_start_pixiv_job`, 325) that rejects concurrent runs; split lightweight status polling vs final-result endpoints (compare `/api/pixiv/job` vs `/api/pixiv/job/result`).

## 3. Checklist

- [ ] elif branch added after the `_check_origin` guard, not bypassing it
- [ ] `_handle_*` written: param validation, `_send_json`, `console_log`, `_safe_error_text`
- [ ] Missing/invalid input returns explicit errors
- [ ] Exact path match, no ambiguous prefix collisions
- [ ] Frontend wired (if needed)
- [ ] `docs/api.md` updated
- [ ] `py_compile` passes; curl smoke passes; cross-origin returns 403
- [ ] No red-line violations

## 4. Notes

- Never bypass `_check_origin` (`AGENTS.md` §3.5).
- Line numbers are a snapshot — locate by symbol name before acting.
- Doc sync is mandatory (`AGENTS.md` §3.9).
