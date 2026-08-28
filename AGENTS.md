# AGENTS.md — PicFerry

> 本项目为个人自用工具，协作对象仅限作者本人与 AI。文档默认使用中文；AI 内部文档（操作指南、行为准则）允许英文原文。

本文档是写给 AI 的项目宪法。在编写、修改、审查本仓库代码前，必须阅读并遵守本文档全部要求。
This document is the project constitution for AI agents. Read and follow it before any code work in this repo.

## 1. 项目介绍

局域网图片比对与传输工具（"PicFerry"，界面中文）。通过 HTTP / FTP / 本地磁盘路径连接两台设备，扫描图片列表、按文件名去重、一键同步；内置 Pixiv 收藏查重（分p级匹配 + 作品黑名单）。

- 仓库：`PicFerry`
- 用户文档（人类视角）：`README.md`、`PicFerry/README.md`

## 2. 项目结构

```
./
├── AGENTS.md                 ← 本文档（AI 宪法）
├── README.md                 ← 根说明（人类）
├── docs/                     ← 文档库（AI + 人类），规则见 docs/README.md
├── PicFerry/                 ← 唯一代码目录
│   ├── server.py             ← 服务端主文件（HTTP 服务 + 业务逻辑，见 §4 结构地图）
│   ├── webassets.py          ← 前端装配：读 static/ 三件套拼回完整 HTML
│   ├── static/               ← 前端真实文件（index.html / style.css / app.js）
│   ├── logging_util.py config_store.py pathsafety.py datasources.py pixiv.py
│   │                         ← 自 server.py 外移的一方模块（日志/配置/路径安全/数据源/Pixiv）
│   ├── README.md             ← 用户文档（功能/API/打包）
│   ├── config/               ← 运行时文件目录（自动创建，不入库）
│   │   ├── config.ini        ← 用户配置（旧版根目录散落文件首次启动自动迁入）
│   │   └── blacklist.csv     ← Pixiv 黑名单（运行时生成）
│   └── dist/                 ← PyInstaller 产物（不入库）
├── archived/                 ← 历史周期归档，规范见 archived/archived.md（默认不读，§3.2 红线）
└── .omo/ .codegraph/         ← AI 工具目录，禁止修改
```

## 3. 要求限制（红线，按优先级）

1. **禁止引入第三方依赖。** 项目是纯 Python 标准库（`http.server`/`ftplib`/`urllib` 等），PyInstaller 单文件零依赖打包是核心卖点。任何 `pip install X`、`import requests`、`from bs4 import ...` 都属于违规。新增功能必须用标准库实现。
2. **禁止读取、修改、搜索 `archived/` 目录。** 它是已归档工程周期的溯源库（结论层明文 + 原料层 zip，规范见 `archived/archived.md`），默认不读以免浪费上下文。若用户要求看归档内容，先询问确认，并按 `archived/archived.md` §6 溯源流程操作。
3. **禁止硬编码新配置键。** 所有可调参数必须注册进 `_CONFIG_KEYS` 注册表（格式 `key: (default, lo, hi, type)`），走 `load_config()`/`save_config()` 读写。直接把值写死或另开解析逻辑 = 违规。
4. **禁止提交运行时文件。** `config/`（config.ini、blacklist.csv）、`dist/` 已在 `.gitignore`，不得强制添加。
5. **禁止删除/绕过同源校验。** `_check_origin` 是所有 `/api/*` 的安全闸门（防 CSRF + DNS rebinding），新端点必须在 `do_GET`/`do_POST` 中经过它，不得跳过。
6. **PHPSESSID 是用户 Pixiv 凭证。** `/api/config` 绝不回显明文（只返回 `hasPhpsessid`）；日志中不得打印 PHPSESSID。
7. **端口 13826 是硬约束。** `PORT = 13826`，前端 HTML 内也硬编码了它；改动必须两端同步。
8. **破坏性操作先备份。** 删除/重写代码前先向用户确认；实现**用户数据删除/清空类功能**（清空记录、删除黑名单等）前，先与用户确认交互方式（如二次确认弹窗），禁止无确认直接执行；大段删除前可 git 提交或留临时文件。
9. **文档同步义务。** 新增/修改功能或 API 时，必须同步更新 `docs/` 对应文档（规则见 `docs/README.md`）。只改代码不更文档 = 违规。
10. **不擅自发布。** 默认允许 `commit`；**`push` 前必须征求用户意见**（个人仓库，保持可控）；打包 EXE、创建 Release 同样需用户明确授权。
11. **日志轮询协议不可破坏。** `LOG_SEQ` 进程存活期内单调递增、清空不重置；`LOG_LAST_ID` 单独维护；`_handle_logs` 的 `truncated` 语义依赖这两者。改坏 = 网页日志静默丢失。
12. **路径安全三层防线不可绕过。** 任何本地读/写路径必须走完整链路：`_sanitize_rel_path`（拒绝对路径/盘符/`..`/尾空格点/保留设备名）→ `_check_local_base`（基座必须 ∈ config 声明的 `dev1ceA`/`dev1ceB`/`PixivL`）→ `_check_realpath_within`（防 junction/symlink 逃逸）。新增功能不得跳过任何一层。
13. **内存/并发资源必须有界。** 禁止无界累积：缓存、集合、任务队列等必须设上限并定义淘汰策略（参照 `LOG_BUFFER` maxlen=500、`maxRows` 截断、Pixiv Job 单槽先例）。新增缓存/累积结构 = 必须先想好上限。
14. **前端 XSS 防线不可绕过。** 前端插入任何用户可控数据必须先过 `escapeHtml`；日志分类 `cat` 必须白名单化（防 class 注入）。新增表格列/面板渲染用户数据时，禁止直接拼 `innerHTML`。

## 4. 注意事项（代码导航）

`server.py` 是服务端主文件（纯标准库）；前端 HTML/CSS/JS 拆分在 `static/`（index.html/style.css/app.js），由 `webassets.py` 在导入期装配回完整 `HTML`，服务端零路由变化。日志/配置/路径安全/数据源/Pixiv 在同目录一方模块。**代码内部结构地图（行区表）、新增代码位置与关键约定见 `docs/guides/module-conventions.md` §1-§2**；该文档随代码维护，AI 改动代码后必须同步（§3.9 文档义务）。

## 5. 对话要求

- 保持任务专注；不确定时先问，不要猜。
- 对不熟悉的术语/概念，主动联网搜索或向用户提问，不要臆造。
- 搜索/读取范围默认排除 `archived/`（§3.2 红线；用户授权时按 `archived/archived.md` §6 溯源）。
- 中文项目：注释、日志、UI 文案保持中文；代码标识符用英文。
- 改动前先说明方案与影响面，涉及红线（§3）必须提示。
- **Plan 模式**：使用 plan 模式时，尽可能详细地说明**要做什么、为什么这么做、怎么做**，让用户能清晰理解你的思路和实现细节。计划经用户确认即视为**锁定**——执行阶段不再讨论替代方案；执行期发现计划硬伤等协作协议见 `docs/guides/collaboration-protocol.md`。
- 参考 `docs/` 前先读 `docs/README.md` 了解约定。

## 6. 参考文档

- `docs/README.md` — 文档库索引与编写规则
- `docs/api.md` — API 端点契约
- `docs/settings.md` — 配置字段说明
- `docs/guides/module-conventions.md` — 结构地图与模块约定（代码导航主入口）
- `docs/guides/collaboration-protocol.md` — 执行期协作协议
- `docs/guides/` — 操作指南（新增设置/新增 API）
- `archived/archived.md` — 归档目录规范与溯源指引（用户授权查阅归档时按此操作）
- `PicFerry/README.md` — 用户视角功能说明
- Pixiv Web AJAX 接口文档（非官方）：`github.com/daydreamer-json/pixiv-ajax-api-docs`（端点 `PIXIV_BOOKMARK_URL` 来源，见 `docs/api.md` §Pixiv）

## 7. 行为准则（Code of Conduct for AI）

Behavioral guidelines to reduce common LLM coding mistakes.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

### 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

### 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

### 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

### 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

**Project-specific verification**: single-file app, no test framework — verification process (py_compile, curl smoke, frontend visual checks) in `docs/guides/module-conventions.md` §6.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.
