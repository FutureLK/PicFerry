# [已弃用] 图库同步工具 — Gallery Sync Tool (Node.js 版本)

> **该项目已停止维护，请使用 [Python 版本](https://github.com/FutureLK/Pixiv-IMG-local-duplication/tree/main/Python%20project/) 替代。**
> Node.js 版本打包体积 38MB，Python 版本仅 6.7MB，功能完全覆盖。

通过**局域网**在两台手机之间同步图库图片。支持 HTTP 和 FTP 两种连接方式。

## 它能做什么

你有两台手机，都用 Pixez（或其他 Pixiv 第三方客户端）保存插画，但两台手机的图库不同步。

这个工具帮你：
1. **扫描** — 拉取两台手机图库的文件列表
2. **去重** — 自动找出"备用机有、主力机没有"的图片
3. **同步** — 一键把新图片复制到主力机

## 使用方式

### 方式：源码运行

需要安装 [Node.js](https://nodejs.org/)（免费）。

```bash
npm install        # 安装依赖（只需一次）
node server.js     # 启动服务
```

浏览器自动打开 `http://localhost:3000`

## 文件结构

```
├── server.js             # 服务器 + 所有逻辑（内嵌 HTML）
├── package.json          # 依赖配置
├── README.md             # 本文件
└── .gitignore
```
