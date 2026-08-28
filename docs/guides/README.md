# docs/guides/README.md — 操作指南索引

面向 AI 的操作指南。每篇指南给出一个完整流程的步骤、代码位置（`path:line + 符号名`）与检查清单。

> 目标读者：AI。人类也可参考流程。
> 行号为编写时快照，定位源码请以符号名为准。

## 指南列表

| 文档 | 目标 | 说明 |
|---|---|---|
| [adding-a-setting.md](adding-a-setting.md) | AI | 新增一个可调配置键的完整流程（注册表→读写→前端→文档） |
| [adding-an-api.md](adding-an-api.md) | AI | 新增一个 `/api/*` 端点的完整流程（路由→handler→文档） |
| [module-conventions.md](module-conventions.md) | AI | `PicFerry/` 多模块布局（server.py 入口 + 一方模块）的组织约定与新增代码位置 |
| [collaboration-protocol.md](collaboration-protocol.md) | AI | 执行期协作协议：计划锁定 / 硬伤处理 / 无人值守 |

## 使用规则

1. 动手前先读 `../README.md`（docs 总规则）与 `../../AGENTS.md`（红线）。
2. 指南给出的是**触碰点清单**，不是免责背书——照抄步骤不保证正确，动手前重新打开对应文件确认行号与现状。
3. 每篇指南以**检查清单**结尾，完成所有勾选项才算流程走完。
4. 所有代码位置引用遵循 `path:line + 符号名` 格式；行号漂移时以符号名为准。

---

> English: [below](#english).

# English

How-to guides for AI agents. Each guide covers one full procedure with code locations (`path:line + symbol`) and a checklist.

## Guides

| Document | Target | Description |
|---|---|---|
| [adding-a-setting.md](adding-a-setting.md) | AI | Full procedure for adding a configurable setting (registry → read/write → frontend → docs) |
| [adding-an-api.md](adding-an-api.md) | AI | Full procedure for adding an `/api/*` endpoint (route → handler → docs) |
| [module-conventions.md](module-conventions.md) | AI | Module organization conventions for the multi-module `PicFerry/` layout (server.py entry + first-party modules) and where new code goes |

## Rules

1. Read `../README.md` (docs rules) and `../../AGENTS.md` (red lines) before acting.
2. Guides are a **touch-point checklist**, not a guarantee — re-open the actual file and confirm line numbers before acting.
3. Every guide ends with a checklist; a procedure is done only when all items are checked.
4. Code references use `path:line + symbol`; when line numbers drift, locate by symbol name.
