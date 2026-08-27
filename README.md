# PicFerry

本仓库是一个**纯AI打造**的个人自用局域网工具：通过HTTP / FTP / 本地磁盘路径连接两台设备，扫描图片列表、按文件名去重、一键同步；内置Pixiv收藏查重（分p级匹配 + 作品黑名单）。

> 定位：学习AI Agent工作流的实验项目，由个人热情强力驱动。

## 主要特性

| 功能 | 说明 |
|---|---|
| 双协议 + 本地 | HTTP目录列表解析 / FTP直连 / 本地磁盘路径 |
| 双向查重 | B→A正向 / A→B反向，一键切换，同步方向自动跟随 |
| Pixiv收藏查重 | 分p级匹配（按作品页数），后台扫描可终止/限量/实时进度，结果仅列缺失作品 |
| 指定作品黑名单 | `blacklist.csv` 管理，拉取阶段直接把整个请求拦截掉 |
| 哈希校验 | 可选显示SHA256摘要（去重按文件名，可选开启） |
| 网页日志 | 终端/网页双端实时 `[SCAN]/[HASH]/[SYNC]/[IMAGE]/[DONE]/[ERROR]`，可暂停/清空/自动滚动 |
| 缩略图和悬浮大图 | 尺寸可调、悬停预览自动避让视口 |
| 输入智能识别 | 类型徽标（HTTP/FTP/本地）、无协议地址自动补全、Pixiv链接提取UID |
| 设备统计 | 扫描后显示每台设备文件总数与总大小 |

## 快速开始

**方式一（推荐）**：从 [Releases](https://github.com/FutureLK/PicFerry/releases) 下载 `PicFerry.exe` 双击运行

**方式二**：源码运行（需 Python 3.10+）

```
cd "Python project"
python server.py
```

运行后浏览器会自动打开 `http://127.0.0.1:13826`


## 使用说明

- **设备同步**：输入设备A/B的HTTP/FTP/本地路径链接，点击「扫描比对」→ 勾选文件 → 「同步到设备A」。
- **Pixiv查重**：在「Pixiv查重」页填写对应的UID、PHPSESSID（浏览器Cookie）与本地文件夹路径，点击「拉取收藏」；查重结果按作品聚合，格式 `123_p0~p9 | 123 | 已有2张/共10张`。
- **黑名单**：在「更多设置」添加作品ID（支持裸ID或 `https://www.pixiv.net/artworks/123456` 链接）。
- **配置**：所有设置项自动持久化到程序旁 `config/config.ini`，字段说明见 [Python project/README.md](Python%20project/README.md)。

## 注意事项

1. **PHPSESSID是属于你自己的Pixiv登录凭证**：本地程序只在本地用于访问Pixiv api接口，不会上传到任何第三方服务器；`/api/config` 不回显明文。
2. **`allowLan` 开启后**：绑定 `0.0.0.0`，局域网内任何设备均可无鉴权访问本服务并读写文件——请在可信的网络环境下开启。
3. **Pixiv请求间隔**（默认0.8s）过低可能触发限流（403）；PHPSESSID过期同样表现为403，请先检查凭证是否过期。
4. **FTP兼容性**：部分设备文件服务不支持 `mlsd` 命令，程序会自动降级为 `nlst`/`dir` 解析（可能会导致文件大小显示为0）。
5. **exe构建**：各版本均在 [Releases](https://github.com/FutureLK/PicFerry/releases) 页提供 `PicFerry.exe`；本地重建方法见 `Python project/README.md` 的打包章节。

## 相关文档

- [Python project/README.md](Python%20project/README.md) — 完整功能/API/打包说明
- [docs/](docs/README.md) — 技术文档库（API契约 / 配置参考 / AI协作指南）
