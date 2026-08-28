# docs/guides/adding-a-setting.md — 新增配置键

给 PicFerry 新增一个可调配置键的完整流程。以新增键 `sampleSize` 为例。

> 目标读者：AI。
> 行号为编写时快照，定位源码请以符号名为准。

## 0. 速览：触碰点

```
_CONFIG_KEYS (server.py:50)  ← 注册默认值/范围/类型
   │
   ├─→ _parse_config_value (59)  自动处理解析/钳制（数值键）
   ├─→ load_config (73)          自动读取
   ├─→ save_config (96)          自动保存
   ├─→ _handle_config (GET)      自动回显
   └─→ _handle_config_save (POST) 自动保存
   │
   └─→ 前端表单（static/index.html + static/app.js）  ← 需要手改
   └─→ docs/settings.md           ← 需要手改
```

## 1. 判断键的类型

- **数值/布尔键**（需范围钳制）→ 进 `_CONFIG_KEYS` 注册表，读写/回显自动覆盖，最省事。
- **自由字符串键**（设备地址、路径、凭证）→ 不入注册表，需在 `load_config`/`save_config`/`_handle_config` 三处手加。**强烈建议优先考虑进注册表**；只有确定无需范围钳制的字符串才走手动路径。

## 2. 步骤（数值/布尔键 — 推荐路径）

**步骤 1：注册键。** 在 `_CONFIG_KEYS`（`server.py:50`）加一行：

```python
'sampleSize': (64, 8, 256, 'int'),    # 示例: 默认64, 范围8-256
```

格式 `key: (default, lo, hi, type)`，`type ∈ {'int', 'float', 'bool'}`。
注册后 `_parse_config_value`(59) 自动处理：空串/非数字回落默认、越界钳制、bool 转 `0/1`。

**步骤 2：验证自动覆盖。** `load_config`(73) 会遍历 `_CONFIG_KEYS` 读取并解析；`save_config`(96) 会遍历注册表保存（bool 键强制转 `0/1`）。`_handle_config`（GET `/api/config`）与 `_handle_config_save`（POST `/api/config/save`）同样自动覆盖。**无需改这三处。**

**步骤 3：前端表单。** 在 `static/index.html` 找到设置表单（"更多设置"标签页）添加输入框，并在 `static/app.js` 中把该键纳入：
- 读取配置后填充（`/api/config` 返回中自动带新键）
- 失焦时随 `POST /api/config/save` 提交

**步骤 4：更新文档。** 在 `docs/settings.md` 字段总览表加一行（键/类型/默认/范围/说明），并在字段说明中补充语义与安全影响（如涉敏感/安全，参照 `allowLan` 的写法）。

## 3. 步骤（自由字符串键 — 手动路径）

仅当键无需范围钳制时使用。以 `MyFolder` 为例，需改四处：

1. `load_config`（`server.py:73`）：在初始 dict 中加 `'MyFolder': cfg.get('Settings', 'MyFolder', fallback='')`。
2. `save_config`（`server.py:96`）：把键加进 `keys` 列表（第 98 行），并按字符串分支处理。
3. `_handle_config`（GET 回显）：把键加入返回 dict。
4. 前端表单 + `docs/settings.md`（同步骤 3/4）。

## 4. 检查清单

- [ ] 键已注册进 `_CONFIG_KEYS`（数值/布尔）或三处手改齐全（字符串）
- [ ] 默认值、范围（lo/hi）、类型正确
- [ ] 前端表单已添加并纳入读取/提交逻辑
- [ ] `docs/settings.md` 总览表与字段说明已更新
- [ ] `python -m py_compile server.py` 通过
- [ ] 冒烟：启动服务，`curl http://127.0.0.1:13826/api/config` 能看到新键；`POST /api/config/save` 后重启仍保留
- [ ] 未触碰红线：无第三方依赖、未硬编码绕过注册表、PHPSESSID 类敏感键不回显明文

## 5. 注意事项

- **禁止绕过注册表**：把新键的值直接写死在代码里读取 = 违反 `AGENTS.md` §3.3。
- **PHPSESSID 是特例**：它是字符串键但属敏感凭证，`_handle_config` 刻意不回显明文（只回 `hasPhpsessid`）。新增敏感键应沿用该模式，不要照抄普通字符串键的回显逻辑。
- **行号漂移**：上述行号是快照，动手前用符号名重新定位。

---

> English: [below](#english).

# English

Full procedure for adding a configurable key to PicFerry. Example key: `sampleSize`.

## 0. Touch points

```
_CONFIG_KEYS (server.py:50)   ← register default/range/type
   ├─→ _parse_config_value (59)  auto parse/clamp (numeric keys)
   ├─→ load_config (73)          auto read
   ├─→ save_config (96)          auto save
   ├─→ _handle_config (GET)      auto echo
   └─→ _handle_config_save (POST) auto save
   └─→ frontend form (static/index.html + static/app.js)  ← manual
   └─→ docs/settings.md          ← manual
```

## 1. Decide the key type

- **Numeric/boolean** (needs clamping) → register in `_CONFIG_KEYS`; read/write/echo are automatic. Preferred.
- **Free-form string** (device address, path, credential) → NOT registered; must be added manually in `load_config`/`save_config`/`_handle_config`. Prefer the registry unless clamping is truly unnecessary.

## 2. Numeric/boolean key (recommended path)

1. Register in `_CONFIG_KEYS` (`server.py:50`): `'sampleSize': (64, 8, 256, 'int'),` — format `key: (default, lo, hi, type)`, `type ∈ {'int','float','bool'}`.
2. Auto-coverage: `load_config`(73) / `save_config`(96) / `_handle_config` / `_handle_config_save` all iterate the registry. No manual edits there.
3. Frontend: add an input in the settings form in `static/index.html`; include the key in config fill (`/api/config`) and submit (`POST /api/config/save`) — JS side in `static/app.js`.
4. Docs: add a row to `docs/settings.md` summary table + a semantic/safety note (follow `allowLan` style for sensitive/security-impact keys).

## 3. Free-form string key (manual path)

Only when clamping is unnecessary. Four edits: `load_config`(73) initial dict, `save_config`(96) `keys` list (line 98), `_handle_config` GET echo dict, frontend form + docs.

## 4. Checklist

- [ ] Key registered in `_CONFIG_KEYS` (numeric/bool) or the three manual edits done (string)
- [ ] Default, range (lo/hi), type correct
- [ ] Frontend form added and wired into read/submit
- [ ] `docs/settings.md` updated (table + notes)
- [ ] `python -m py_compile server.py` passes
- [ ] Smoke: `/api/config` shows the key; survives restart after save
- [ ] No red-line violations: no third-party deps, no hardcoded bypass of registry, sensitive keys never echo plaintext

## 5. Notes

- **Never bypass the registry** — hardcoding a new key's read path violates `AGENTS.md` §3.3.
- **PHPSESSID is special**: a string key treated as a credential; `_handle_config` deliberately echoes only `hasPhpsessid`. New sensitive keys should follow that pattern, not the plain string echo.
- Line numbers are a snapshot — locate by symbol name before acting.
