# docs/settings.md — 配置参考

`config.ini` 全部字段的说明。配置文件位于程序旁 `config/` 子目录（旧版根目录散落文件首次启动自动迁入；程序所在位置只读时自动降级到 `%APPDATA%\ImageSync\config`），启动时自动加载，修改输入框失焦后自动保存。

> 目标读者：人类。AI 新增配置键时请走 `docs/guides/adding-a-setting.md` 的流程，并同步更新本文档。

## 字段总览

| 键 | 类型 | 默认 | 范围 | 说明 |
|---|---|---|---|---|
| `dev1ceA` | str | `''` | — | 设备 A 的 HTTP/FTP/本地链接 |
| `dev1ceB` | str | `''` | — | 设备 B 的 HTTP/FTP/本地链接 |
| `PixivUID` | str | `''` | — | Pixiv 用户 ID |
| `PHPSESSID` | str | `''` | — | Pixiv 登录凭证（敏感，见下） |
| `PixivL` | str | `''` | — | Pixiv 查重用的本地文件夹路径 |
| `thumbnailSize` | int | `48` | 16–128 | 缩略图尺寸（px），界面为下拉档位 16/24/48/64/96 |
| `previewDelay` | int | `500` | 100–2000 | 悬浮预览延迟（ms） |
| `pixivInterval` | float | `0.8` | 0.1–10 | Pixiv 请求间隔（秒，防限流） |
| `pixivLimit` | int | `0` | 0–100000 | Pixiv 扫描数量上限（0=全部） |
| `maxRows` | int | `1000` | 10–5000 | 结果表行数上限 |
| `allowLan` | bool | `0` | 0/1 | 绑定 `0.0.0.0` 开启局域网访问 |
| `lightTheme` | bool | `0` | 0/1 | 界面主题：0=深色（默认），1=浅色（日间模式） |

## 字段说明

### 连接与路径（字符串键）

- **dev1ceA / dev1ceB** — 设备地址。支持三种形式：HTTP 目录列表 URL（如 `http://192.168.1.100:8080/`）、FTP 地址（如 `ftp://192.168.1.100/`）、本地路径（如 `C:\Users\...\Pictures` 或 `file:///D:/Photos`）。无协议地址（如 `192.168.1.100:1234`）前端自动补全 `http://`。
- **PixivUID** — Pixiv 用户数字 ID。
- **PHPSESSID** — 浏览器登录 Pixiv 后 Cookie 中的会话凭证。
  - **敏感项**：`/api/config` 绝不回显明文，只返回 `hasPhpsessid` 布尔值；日志中不得打印。
  - 留空保存保留原值；**清空需手动编辑 config.ini**。
- **PixivL** — Pixiv 查重时扫描的本地文件夹。

### 数值键（`_CONFIG_KEYS` 注册表，`server.py:45`）

数值键由 `_parse_config_value`（`server.py:55`）统一解析：空串/非数字回落默认值，越界钳制到 `[lo, hi]`，`bool` 键保存时转 `0/1`。

- **thumbnailSize** — 设备同步页缩略图边长（px），影响布局密度。界面为下拉档位（特小16/小24/标准48/大64/特大96）；历史滑条遗留的档位外数值会自动显示为「自定义（Npx）」选项，选中任一档位后即归位。
- **previewDelay** — 鼠标悬停文件名到弹出大图的延迟（ms）。
- **pixivInterval** — Pixiv 收藏拉取的请求间隔（秒）。过低会触发 Pixiv 限流（403）。默认 0.8。
- **pixivLimit** — 单次拉取的收藏上限，0 = 全部（`fetch_all_pixiv_bookmark_ids`，`server.py:1874`）。
- **maxRows** — 设备同步 / Pixiv 查重结果表的最大行数，超出截断（`run_pixiv_job` 按作品数截断，`server.py:2014`）。
- **allowLan** — 安全开关：
  - `0`（默认）：仅本机可访问，且 `_check_origin` 校验 Host ∈ `{127.0.0.1, localhost, ::1}`（防 DNS rebinding）。
  - `1`：绑定 `0.0.0.0`，局域网内任何设备均可访问。
  - **开启后局域网内任何设备均可无鉴权访问本服务并读写文件。**
  - 权限边界：远程设备可设置网络地址形态的设备键（`http://`、`ftp://`）并扫描网络源；设备键的本地盘形态值、空串清除意图及 `PHPSESSID` 仅本机可写；未声明的本地目录不可列出或读取。
- **lightTheme** — 界面主题开关。`0`（默认）深色；`1` 浅色（日间模式）。入口在「更多设置 → 界面设置」下拉，切换即存。主题通过 CSS 变量覆盖层（`html[data-theme=light]`）+ `color-scheme` 实现。

## 示例文件

```ini
[Settings]
dev1ceA = http://192.168.1.100:8080/
dev1ceB = ftp://192.168.1.101/
PixivUID = 12345678
PHPSESSID = 
PixivL = C:\Users\Me\Pictures
thumbnailSize = 48
previewDelay = 500
pixivInterval = 0.8
pixivLimit = 0
maxRows = 1000
allowLan = 0
lightTheme = 0
```

## 实现位置

- 目录确定：`server.py:40 _prepare_config_dir`（程序旁不可写时降级 `%APPDATA%\ImageSync\config`）
- 注册表：`server.py:78 _CONFIG_KEYS`（`key: (default, lo, hi, type)`）
- 解析/钳制：`server.py:88 _parse_config_value`（含溢出值兜底）
- 解析文件：`server.py:108 _parse_config_file`（语法损坏/BOM/坏编码显式区分于文件缺失）
- 读取：`server.py:139 load_config`（解析失败回落全默认，不抛错）
- 保存：`server.py:148 save_config`（合并当前值、`bool` 转 `0/1`；`.tmp + os.replace` 原子写；文件已损坏时**拒绝覆盖保存**，防 PHPSESSID 被空默认值抹除）
- HTTP 读取：`GET /api/config`（`_handle_config`）
- HTTP 保存：`POST /api/config/save`（`_handle_config_save`）

---

> English: [below](#english).

# English

Reference for every `config.ini` field. The file lives in the `config/` subfolder next to `server.py` (or the EXE) — falling back to `%APPDATA%\ImageSync\config` when that location is read-only; it is loaded at startup and saved automatically when a form input loses focus.

## Field Summary

| Key | Type | Default | Range | Description |
|---|---|---|---|---|
| `dev1ceA` | str | `''` | — | Device A link (HTTP/FTP/local) |
| `dev1ceB` | str | `''` | — | Device B link (HTTP/FTP/local) |
| `PixivUID` | str | `''` | — | Pixiv user ID |
| `PHPSESSID` | str | `''` | — | Pixiv session cookie (sensitive, see below) |
| `PixivL` | str | `''` | — | Local folder for Pixiv dedup scan |
| `thumbnailSize` | int | `48` | 16–128 | Thumbnail size (px); UI offers preset options 16/24/48/64/96 |
| `previewDelay` | int | `500` | 100–2000 | Hover preview delay (ms) |
| `pixivInterval` | float | `0.8` | 0.1–10 | Pixiv request interval (s, anti-throttle) |
| `pixivLimit` | int | `0` | 0–100000 | Max bookmarks to fetch (0 = all) |
| `maxRows` | int | `1000` | 10–5000 | Max result rows |
| `allowLan` | bool | `0` | 0/1 | Bind `0.0.0.0` to allow LAN access |
| `lightTheme` | bool | `0` | 0/1 | UI theme: 0 = dark (default), 1 = light (day mode) |

## Notes

- **PHPSESSID is sensitive**: never echoed by `/api/config` (only `hasPhpsessid`); never printed in logs. Leaving it empty keeps the stored value; clearing requires editing `config.ini` manually.
- **allowLan** defaults to `0` (localhost-only, Host checked against `{127.0.0.1, localhost, ::1}` to prevent DNS rebinding). Setting `1` binds `0.0.0.0` — **any LAN device can then access the service and read/write files without authentication.**
- **Permission boundary**: remote devices may set network-address device keys (`http://`, `ftp://`) and scan network sources; local-drive-form values of the device keys, their empty-string clears, and `PHPSESSID` are writable from this machine only; undeclared local directories cannot be listed or read.
- **thumbnailSize** — UI is a dropdown with presets 16/24/48/64/96; legacy slider values outside the presets show up as a temporary "custom" option.
- **lightTheme** — UI theme switch (dark default / light day mode), set from the "更多设置 → 界面设置" dropdown; implemented via a CSS variable override layer (`html[data-theme=light]`) plus `color-scheme`.

## Implementation

- Directory resolution: `server.py:40 _prepare_config_dir` (falls back to `%APPDATA%\ImageSync\config`)
- Registry: `server.py:78 _CONFIG_KEYS`
- Parse/clamp: `server.py:88 _parse_config_value` (overflow values included)
- File parsing: `server.py:108 _parse_config_file` (corrupt/BOM/bad-encoding distinguished from missing)
- Load: `server.py:139 load_config` (falls back to defaults on any parse failure, never raises)
- Save: `server.py:148 save_config` (atomic `.tmp + os.replace`; **refuses to overwrite** a corrupt file so the stored PHPSESSID can't be wiped by empty defaults)
- HTTP: `GET /api/config` / `POST /api/config/save`
