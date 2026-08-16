# 图片同步

局域网文件比对与传输工具。

通过 HTTP、FTP 或本地磁盘路径连接两台设备，扫描图片列表、自动去重、一键同步。内置 Pixiv 收藏查重（分p级匹配 + 作品黑名单）。

## 使用方式

### 方式一：EXE（推荐）

从 [Releases 页面](https://github.com/FutureLK/Pixiv-IMG-local-duplication/releases) 下载最新版的 `图片同步.exe`，双击运行，浏览器自动打开。

> 首次运行 Windows 可能提示安全警告，点击「更多信息」→「仍要运行」即可。
> 配置文件 `config.ini` 与黑名单 `blacklist.csv` 均与 EXE 同目录。

### 方式二：源码运行

需要 Python 3.10+，无需安装任何额外依赖。

```bash
python server.py
```

浏览器自动打开 `http://127.0.0.1:13826`

> 程序启动时会自动读取同目录下的 `config.ini`，填入上次保存的值；修改输入框后按 Tab 移出即自动保存。

## 界面功能

网页为四个标签页：

- **设备同步** — 设备 A/B 扫描比对、双向查重、哈希校验、一键同步
- **Pixiv 查重** — 拉取 Pixiv 收藏（可限量/随时终止）与本地图片分p级比对
- **更多设置** — 缩略图尺寸、预览悬浮延迟、Pixiv 请求间隔、结果行数上限；作品黑名单管理
- **日志** — 实时彩色命令行日志（自动滚动 / 暂停 / 清空）

### 设备同步

- **双向查重** — B→A / A→B 一键切换，重新计算去重结果，同步方向自动跟随
- **缩略图预览** — 缩略图通过 `/api/image` 代理懒加载（IntersectionObserver 按需加载），尺寸可在「更多设置」调节（16-128px）
- **设备统计** — 扫描后显示设备 A/B 各自的文件总数和总大小
- **悬浮大图预览** — 鼠标悬停缩略图或文件名弹出大图预览面板，自动避让视口边缘（延迟可在「更多设置」调节）
- **逐行动画** — 扫描结果 fadeIn 渐现 + 交错延迟（每行 30ms），进度条 fillBar 填充动画
- **输入智能识别** — 地址框自动识别 HTTP/FTP/本地路径并显示类型徽标；无协议地址（如 `192.168.1.100:1234`）自动补全 `http://`

### Pixiv 收藏查重

1. 在「Pixiv 查重」标签页填写 Pixiv UID、PHPSESSID（浏览器 Cookie）与本地文件夹路径
2. 可选设置「扫描数量」限制拉取条数（0 = 全部）
3. 点击「拉取收藏」，后台扫描可随时点「终止」停止，进度实时显示
4. 查重为**分p级匹配**：本地 `123_p2.jpg` 仅当书签中作品 123 的页数 > 2 才判定为已收藏；查重结果仅列出「设备里没有的」缺失作品，按作品聚合为一行，格式 `123_p0~p9 | 123 | 已有2张/共10张`（范围列=作品全部分p区间、ID 列=作品 ID、分p列=本地已有X张/共Y张，Y=作品总页数）；ID 可点击跳转作品页；每行 ID 左侧有「加黑名单」按钮，点击后该行保留并标记为已加入；顶部统计为 收藏总数/缺失作品数/缺失分p总数

> PHPSESSID 相当于你的登录凭证，不会上传到任何第三方服务器，仅在本地程序内用于访问 Pixiv 接口。

### 黑名单

在「更多设置」→「Pixiv 查重黑名单」添加作品 ID（支持裸 ID 或 `https://www.pixiv.net/artworks/123456` 链接），黑名单作品在扫描拉取阶段即被剔除（含分p环节），存储于同目录 `blacklist.csv`。

### 控制台与网页日志

所有操作实时输出到终端与网页「日志」标签页，带颜色区分：

| 类别 | 颜色 | 触发时机 |
|---|---|---|
| `[SCAN]` | 青色 | 扫描/拉取收藏 |
| `[HASH]` | 黄色 | 开始哈希校验 |
| `[SYNC]` | 蓝色 | 每个文件同步完成 |
| `[IMAGE]` | 灰色 | 图片代理加载失败 |
| `[DONE]` | 绿色 | 扫描/同步全部完成 |
| `[ERROR]` | 红色 | 任何环节出错 |

日志同时写入 `sync.log`（与 EXE 同目录），以防终端输出被关闭或缓冲。

## 配置文件（可选）

在同目录下创建 `config.ini`，程序启动时自动加载并填入表单，离开输入框时自动保存。所有键均可留空或省略，使用默认值。

```ini
[Settings]
dev1ceA = 
dev1ceB = 
PixivUID = 
PHPSESSID = 
PixivL = 
thumbnailSize = 48
previewDelay = 500
pixivInterval = 0.8
pixivLimit = 0
maxRows = 1000
allowLan = 0
```

字段说明:
- `dev1ceA` — 设备 A 的 HTTP/FTP 链接
- `dev1ceB` — 设备 B 的 HTTP/FTP 链接
- `PixivUID` — Pixiv 用户 ID
- `PHPSESSID` — Pixiv 登录凭证 (Cookie)（/api/config 不回显明文；留空保存保留原值；清空需手动编辑 config.ini）
- `PixivL` — 查重用的本地文件夹路径
- `thumbnailSize` — 缩略图尺寸 px（16-128，默认 48）
- `previewDelay` — 悬浮预览延迟 ms（100-2000，默认 500）
- `pixivInterval` — Pixiv 请求间隔 秒（0.1-10，默认 0.8，防限流）
- `pixivLimit` — Pixiv 扫描数量上限（0=全部）
- `maxRows` — 结果表行数上限（设备同步/Pixiv 查重，10-5000，默认 1000）
- `allowLan` — 绑定 0.0.0.0 开启局域网访问（0=仅本机，默认 0）；开启后可从局域网设备浏览器打开 http://<电脑IP>:13826

**开启后局域网内任何设备均可无鉴权访问本服务并读写文件**

## 支持的数据源

- **HTTP** — 自动解析目录列表 HTML（手机文件管理器的 HTTP 服务）
- **FTP** — 通过 ftplib 内置库连接（MT 管理器的 FTP 无需配对码）
- **本地路径** — 直接扫描磁盘目录（`C:\Users\...\Pictures` 或 `D:\Photos`），支持 `file:///` 前缀

## 打包

```bash
pip install pyinstaller
pyinstaller --onefile --name "图片同步" server.py
```

产出 `dist/图片同步.exe`，约 7 MB（以重建后实测为准），不依赖 Python 环境。EXE 模式下配置文件与日志均落在 EXE 同目录（非临时目录）。

## API 接口

| 端点 | 方法 | 参数 | 说明 |
|---|---|---|---|
| `/` | GET | — | 返回 Web 界面 |
| `/api/list` | GET | `url` = 设备 HTTP/FTP 链接 | 扫描文件列表，返回 JSON |
| `/api/hash` | POST | `url`, `file` | 计算文件 SHA256 |
| `/api/copy` | POST | `from`, `to`, `file` | 同步单个文件（来源 → 目标） |
| `/api/image` | GET | `url`, `file` | 图片代理，转发图片供浏览器展示 |
| `/api/log` | GET/POST | `cat` = 类别, `msg` = 消息 | 前端日志推送到终端 + sync.log + 内存缓冲 |
| `/api/logs` | GET | `since` = 日志 id | 增量拉取日志（环形缓冲，`truncated` 标志表示需重载） |
| `/api/logs/clear` | POST | — | 清空内存日志缓冲（不动 sync.log） |
| `/api/config` | GET | — | 读取配置 JSON（PHPSESSID 不回显，返回 hasPhpsessid） |
| `/api/config/save` | POST | 全部配置字段 | 保存配置到 config.ini |
| `/api/pixiv/bookmarks` | POST | `uid`, `phpsessid`, `path`, `limit?` | 启动 Pixiv 收藏扫描（后台 Job） |
| `/api/pixiv/bookmarks/stop` | POST | — | 请求终止当前扫描 |
| `/api/pixiv/job` | GET | — | 轮询 Job 状态（status/progress/error/summary） |
| `/api/pixiv/job/result` | GET | — | 取终态结果（done 后含 matched 数组） |
| `/api/blacklist` | GET | — | 读取黑名单 ID 列表 |
| `/api/blacklist/add` | POST | `id`（裸 ID 或作品链接） | 添加黑名单 |
| `/api/blacklist/remove` | POST | `id` | 移除黑名单 |
| `/api/blacklist/clear` | POST | — | 清空黑名单 |
| `/api/...` | OPTIONS | — | 预检处理（跨源请求返回 403，仅同源可用） |

## 项目结构

```
├── server.py          Python 服务器（内嵌 HTML/CSS/JS，单文件）
├── dist/
│   └── 图片同步.exe     打包后的独立可执行文件 (~7 MB)
├── sync.log           运行日志（自动生成，与 EXE 同目录）
├── config.ini         用户配置（自动生成/保存，不入库）
├── blacklist.csv      Pixiv 黑名单（自动生成，不入库）
└── README.md
```

> 注：当前 `dist/图片同步.exe` 为 2026-08-12 旧构建（未含查重反转等更新），建议优先源码运行；重建前以源码行为为准。
