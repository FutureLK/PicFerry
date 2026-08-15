# docs/settings.md — 配置参考

`config.ini` 全部字段的说明。配置文件与 `server.py`（或 EXE）同目录，启动时自动加载，修改输入框失焦后自动保存。

> 目标读者：人类。AI 新增配置键时请走 `docs/guides/adding-a-setting.md` 的流程，并同步更新本文档。

## 字段总览

| 键 | 类型 | 默认 | 范围 | 说明 |
|---|---|---|---|---|
| `dev1ceA` | str | `''` | — | 设备 A 的 HTTP/FTP/本地链接 |
| `dev1ceB` | str | `''` | — | 设备 B 的 HTTP/FTP/本地链接 |
| `PixivUID` | str | `''` | — | Pixiv 用户 ID |
| `PHPSESSID` | str | `''` | — | Pixiv 登录凭证（敏感，见下） |
| `PixivL` | str | `''` | — | Pixiv 查重用的本地文件夹路径 |
| `thumbnailSize` | int | `48` | 16–128 | 缩略图尺寸（px） |
| `previewDelay` | int | `500` | 100–2000 | 悬浮预览延迟（ms） |
| `pixivInterval` | float | `0.8` | 0.1–10 | Pixiv 请求间隔（秒，防限流） |
| `pixivLimit` | int | `0` | 0–100000 | Pixiv 扫描数量上限（0=全部） |
| `maxRows` | int | `1000` | 10–5000 | 结果表行数上限 |
| `allowLan` | bool | `0` | 0/1 | 绑定 `0.0.0.0` 开启局域网访问 |

## 字段说明

### 连接与路径（字符串键）

- **dev1ceA / dev1ceB** — 设备地址。支持三种形式：HTTP 目录列表 URL（如 `http://192.168.1.100:8080/`）、FTP 地址（如 `ftp://192.168.1.100/`）、本地路径（如 `C:\Users\...\Pictures` 或 `file:///D:/Photos`）。无协议地址（如 `192.168.1.100:1234`）前端自动补全 `http://`。
- **PixivUID** — Pixiv 用户数字 ID。
- **PHPSESSID** — 浏览器登录 Pixiv 后 Cookie 中的会话凭证。
  - **敏感项**：`/api/config` 绝不回显明文，只返回 `hasPhpsessid` 布尔值；日志中不得打印。
  - 留空保存保留原值；**清空需手动编辑 config.ini**。
- **PixivL** — Pixiv 查重时扫描的本地文件夹。

### 数值键（`_CONFIG_KEYS` 注册表，`server.py:50`）

数值键由 `_parse_config_value`（`server.py:59`）统一解析：空串/非数字回落默认值，越界钳制到 `[lo, hi]`，`bool` 键保存时转 `0/1`。

- **thumbnailSize** — 设备同步页缩略图边长（px），影响布局密度。
- **previewDelay** — 鼠标悬停文件名到弹出大图的延迟（ms）。
- **pixivInterval** — Pixiv 收藏拉取的请求间隔（秒）。过低会触发 Pixiv 限流（403）。默认 0.8。
- **pixivLimit** — 单次拉取的收藏上限，0 = 全部（`fetch_all_pixiv_bookmark_ids`，`server.py:1723`）。
- **maxRows** — 设备同步 / Pixiv 查重结果表的最大行数，超出截断（`run_pixiv_job` 按作品数截断，`server.py:1945`）。
- **allowLan** — 安全开关：
  - `0`（默认）：仅本机可访问，且 `_check_origin` 校验 Host ∈ `{127.0.0.1, localhost, ::1}`（防 DNS rebinding）。
  - `1`：绑定 `0.0.0.0`，局域网内任何设备均可访问。
  - **开启后局域网内任何设备均可无鉴权访问本服务并读写文件。**

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
```

## 实现位置

- 注册表：`server.py:50 _CONFIG_KEYS`（`key: (default, lo, hi, type)`）
- 解析/钳制：`server.py:59 _parse_config_value`
- 读取：`server.py:73 load_config`（损坏/缺段/BOM 时回落全默认，不抛错）
- 保存：`server.py:96 save_config`（合并当前值，`bool` 转 `0/1`）
- HTTP 读取：`GET /api/config`（`_handle_config`）
- HTTP 保存：`POST /api/config/save`（`_handle_config_save`）

---

> English: [below](#english).

# English

Reference for every `config.ini` field. The file lives next to `server.py` (or the EXE); it is loaded at startup and saved automatically when a form input loses focus.

## Field Summary

| Key | Type | Default | Range | Description |
|---|---|---|---|---|
| `dev1ceA` | str | `''` | — | Device A link (HTTP/FTP/local) |
| `dev1ceB` | str | `''` | — | Device B link (HTTP/FTP/local) |
| `PixivUID` | str | `''` | — | Pixiv user ID |
| `PHPSESSID` | str | `''` | — | Pixiv session cookie (sensitive, see below) |
| `PixivL` | str | `''` | — | Local folder for Pixiv dedup scan |
| `thumbnailSize` | int | `48` | 16–128 | Thumbnail size (px) |
| `previewDelay` | int | `500` | 100–2000 | Hover preview delay (ms) |
| `pixivInterval` | float | `0.8` | 0.1–10 | Pixiv request interval (s, anti-throttle) |
| `pixivLimit` | int | `0` | 0–100000 | Max bookmarks to fetch (0 = all) |
| `maxRows` | int | `1000` | 10–5000 | Max result rows |
| `allowLan` | bool | `0` | 0/1 | Bind `0.0.0.0` to allow LAN access |

## Notes

- **PHPSESSID is sensitive**: never echoed by `/api/config` (only `hasPhpsessid`); never printed in logs. Leaving it empty keeps the stored value; clearing requires editing `config.ini` manually.
- **allowLan** defaults to `0` (localhost-only, Host checked against `{127.0.0.1, localhost, ::1}` to prevent DNS rebinding). Setting `1` binds `0.0.0.0` — **any LAN device can then access the service and read/write files without authentication.**

## Implementation

- Registry: `server.py:50 _CONFIG_KEYS`
- Parse/clamp: `server.py:59 _parse_config_value`
- Load: `server.py:73 load_config` (falls back to defaults on corrupt config, never raises)
- Save: `server.py:96 save_config`
- HTTP: `GET /api/config` / `POST /api/config/save`
