# -*- coding: utf-8 -*-
"""静态前端资源装配：把 static/ 三件套拼回与拆分前逐字节等价的完整 HTML。

- static/index.html  页面骨架，<style>/<script> 标签保留，块内容位置为占位符
- static/style.css   原 <style> 块内容（逐字节原样）
- static/app.js      原 <script> 块内容（逐字节原样）

server.py 通过 `from webassets import HTML` 在导入期得到装配好的完整页面。
"""
import os
import sys

_CSS_PLACEHOLDER = '@@CSS@@'
_JS_PLACEHOLDER = '@@JS@@'


def resource_dir():
    """EXE 冻结时返回解包目录 sys._MEIPASS，否则返回本文件所在目录。"""
    if getattr(sys, 'frozen', False):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))


def _read_static(name):
    path = os.path.join(resource_dir(), 'static', name)
    # newline='' 防止文本模式把 \r\n / \n 做换行转译，保证逐字节等价
    with open(path, 'r', encoding='utf-8', newline='') as f:
        return f.read()


def build_html():
    """读入 index.html/style.css/app.js 并替换占位符，组装出完整 HTML。"""
    html = _read_static('index.html')
    return (html.replace(_CSS_PLACEHOLDER, _read_static('style.css'))
                .replace(_JS_PLACEHOLDER, _read_static('app.js')))


HTML = build_html()
