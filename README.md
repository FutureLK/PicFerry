# 图片同步 - 多版本

局域网文件比对与传输工具。支持 HTTP/FTP 连接两台手机，扫描去重后一键同步。

## 功能一览

| 功能 | 说明 |
|---|---|
| 双协议 | HTTP 目录列表解析 + FTP 直连（MT 管理器免配对码） |
| 本地路径 | 直接扫描本地磁盘目录（`C:\Users\...\Pictures` 等） |
| 双向查重 | B→A 正向 / A→B 反向，一键切换 |
| 哈希校验 | SHA256 比对文件内容，可选开启 |
| 设备统计 | 扫描后显示每台设备的文件总数和总大小 |
| 缩略图预览 | 48×48 缩略图列，懒加载不阻塞 |
| 悬浮大图 | 鼠标悬停文件名 500ms 弹出预览面板，自动避让视口 |
| 逐行动画 | 扫描结果 fadeIn 渐现 + 交错延迟 |
| 彩色日志 | 终端输出 `[SCAN]/[HASH]/[SYNC]/[DONE]/[ERROR]` 带颜色区分 |
| 日志文件 | 同目录 `sync.log`，防止终端输出丢失 |
| 图片代理 | `/api/image` 转发远程图片供浏览器直接展示 |
| 单文件打包 | PyInstaller → 6.7 MB，零依赖 |

## 版本

| 目录 | 语言 | 体积 | 说明 |
|---|---|---|---|
| [Python project](Python%20project/) | Python 3 | **6.7 MB** | 当前推荐版本，零外部依赖，内嵌 Web UI |
| [Nodejs project](Nodejs%20project/) | Node.js | **38 MB** | 旧版存档，不再维护 |

## 快速开始

```
cd "Python project"
python server.py
```

或双击 `Python project/dist/图片同步.exe`。
