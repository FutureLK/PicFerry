# docs/guides/collaboration-protocol.md — 协作协议

计划锁定之后、执行期间的协作规则。AGENTS.md §5 只留 Plan 模式条款与本文档指引；本页承载执行期细节。

> 目标读者：AI。人类也可参考。
> 行号为编写时快照，定位源码请以符号名为准。

## 1. 计划锁定

- 计划经用户确认即视为**锁定**：执行阶段不再讨论替代方案（防执行期"开小差"重新评审方案）。
- 用户随时有权解锁（锁定约束的是 AI，不是用户）。

## 2. 硬伤协议（交互模式）

执行阶段发现计划硬伤（前提不成立 / 方向错误 / 触发红线 §3）时：

1. **立即停止**当前步骤与新的子 agent 派发；
2. 已派出的子 agent：`background_cancel` 取消，或等结果但**不采用**；
3. 向用户报告：硬伤是什么、影响哪些 todo、建议的修正方向；
4. **等用户决策后再继续**，不得自行绕路完成剩余 todo。

**轻微偏差**（行号漂移 / 细节出入）自行适配，不打扰用户。

## 3. 检查清单

- [ ] 计划锁定后未重新评审方案
- [ ] 交互模式硬伤：已停止 + 报告 + 等决策，未绕路

---

> English: [below](#english).

# English

Collaboration rules for the execution phase after a plan is locked. `AGENTS.md` §5 keeps only the Plan-mode clause and a pointer here; this page carries the execution-phase details.

## 1. Plan locking

- A plan confirmed by the user is **locked**: no alternative proposals during execution (prevents re-opening design discussions mid-execution).
- The user may unlock at any time (the lock binds the AI, not the user).

## 2. Plan-breaking flaw protocol (interactive mode)

When a plan flaw is found mid-execution (premise broken / wrong direction / red-line §3 triggered):

1. **Stop immediately**: pause the current step and stop dispatching new sub-agents;
2. Already-dispatched sub-agents: `background_cancel`, or await results but **do not use them**;
3. Report to the user: what the flaw is, which todos it affects, suggested fix direction;
4. **Wait for the user's decision** — do not work around the remaining todos on your own.

**Minor deviations** (line-number drift / detail mismatches): adapt silently, don't interrupt the user.

## 3. Checklist

- [ ] Plan locked; no design re-review during execution
- [ ] Interactive-mode flaw: stopped + reported + waiting, no workaround
