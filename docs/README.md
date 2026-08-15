# docs/README.md — 文档库索引与编写规则

本文档是 `docs/` 文档库的索引与编写规则。**在 `docs/` 新增/修改任何文档前，先读本文档。**

> 目标读者：人类 + AI。
> 文档同步是硬义务：修改功能/API 时必须同步更新对应文档（见 `../AGENTS.md` §3.9）。

## 概要与要求

1. **按目标读者分目录**：人类向文档放 `docs/` 根（如 `settings.md`）；AI 操作指南放 `docs/guides/`；重大变更记录放 `docs/breakings/`（暂未启用）。
2. **每个子目录必须有 `README.md`**：作为该目录的说明与索引。
3. **索引表固定三列**：`| 文档或路径 | 目标 | 说明 |`，目标列标注 `人类` / `AI` / `人类+AI`。
4. **新增/删除文档必须在父索引登记**：`docs/README.md` 或对应子目录 `README.md` 中添加/删除条目，否则视为未完成。
5. **语言**：中文优先。人类向文档双语（中文在前，英文部分用 `> English: [below](#english)` 锚点跳转）；AI 向文档中文即可。
6. **代码引用格式**：`path:line + 符号名`（如 `server.py:50 _CONFIG_KEYS`）。行号为编写时快照，代码演进后可能漂移；定位源码请以符号名为准。
7. **诚实原则**：只写落地代码的行为，不写"未来将要"的推测；指南类文档承认"照抄步骤不保证正确，动手前重新打开对应文件确认"。
8. **改动代码时必须同步**：新增/修改 API → 更新 `api.md`；新增/修改配置 → 更新 `settings.md`；改变模块组织 → 更新 `guides/module-conventions.md`。

## 文档索引

| 文档或路径 | 目标 | 说明 |
|---|---|---|
| [settings.md](settings.md) | 人类 | `config.ini` 全部字段的参考说明（含范围/默认值/敏感项） |
| [api.md](api.md) | 人类+AI | `/api/*` 端点契约（方法/参数/返回/错误） |
| [guides/](guides/README.md) | AI | 操作指南：新增设置 / 新增 API / 模块约定 |

---

> English: [below](#english).

# English

This is the index and authoring guide for the `docs/` knowledge base. **Read this before adding or modifying any doc under `docs/`.**

## Rules & Requirements

1. **Organize by audience**: human-facing docs live in `docs/` root (e.g. `settings.md`); AI how-to guides live in `docs/guides/`; breaking-change records go in `docs/breakings/` (not yet in use).
2. **Every subdirectory must have a `README.md`** serving as its guide and index.
3. **Index tables use a fixed 3-column format**: `| Document or Path | Target | Description |` where Target is `Human` / `AI` / `Human+AI`.
4. **Register every doc in its parent index** — adding or removing a doc without updating the index table counts as incomplete work.
5. **Language**: Chinese-first. Human-facing docs are bilingual (Chinese first; English section linked via `> English: [below](#english)` anchor); AI-facing docs may be Chinese-only.
6. **Code references**: `path:line + symbol` format (e.g. `server.py:50 _CONFIG_KEYS`). Line numbers are a snapshot — they drift as code evolves; locate source by symbol name.
7. **Honesty**: document only landed behavior, never future speculation; guides admit "copying steps does not guarantee correctness — re-open the file before acting".
8. **Sync obligation**: code changes must update docs — new/changed API → `api.md`; new/changed setting → `settings.md`; module-organization changes → `guides/module-conventions.md`.

## Index

| Document or Path | Target | Description |
|---|---|---|
| [settings.md](settings.md) | Human | Reference for every `config.ini` field (range / default / sensitive) |
| [api.md](api.md) | Human+AI | `/api/*` endpoint contract (method / params / response / errors) |
| [guides/](guides/README.md) | AI | How-to guides: adding a setting / adding an API / module conventions |
