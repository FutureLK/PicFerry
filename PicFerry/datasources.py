# datasources.py — 从 server.py 原样移出的数据源访问函数（HTTP/FTP/本地 目录列举、下载、上传与远程文件读取），见 server.py 引用处

import io
import os
import re
import ftplib
import urllib.parse
import urllib.request
from logging_util import console_log
from pathsafety import is_local_path, strip_file_prefix, _sanitize_rel_path, _check_local_base, _check_realpath_within

IMAGE_EXTS = ('.jpg', '.jpeg', '.png', '.gif', '.webp')

# ─── URL helpers ─────────────────────────────────────────────────────────────

def is_ftp(url):
    return url.lower().startswith('ftp://')

def resolve_url(base, filename):
    base = base.rstrip('/') + '/'
    return base + urllib.parse.quote(filename)

def parse_ftp_info(url):
    parsed = urllib.parse.urlparse(url)
    return {
        'host': parsed.hostname or 'localhost',
        'port': parsed.port or 21,
        'user': parsed.username or 'anonymous',
        'password': parsed.password or 'anonymous@',
        'path': parsed.path or '/'
    }

# ─── HTTP helpers ────────────────────────────────────────────────────────────

def http_fetch(url, timeout=15):
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode('utf-8', errors='replace')
        return body, resp.status

def http_download(url, timeout=30):
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()

def http_put(url, data, timeout=60):
    req = urllib.request.Request(url, data=data, method='PUT')
    req.add_header('Content-Type', 'application/octet-stream')
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status

# ─── FTP helpers ─────────────────────────────────────────────────────────────

def ftp_list(url):
    info = parse_ftp_info(url)
    ftp = ftplib.FTP()
    ftp.connect(info['host'], info['port'], timeout=15)
    ftp.login(info['user'], info['password'])
    result = []
    try:
        ftp.cwd(info['path'])
        try:
            for entry in ftp.mlsd():
                name, attrs = entry
                if attrs.get('type') == 'file':
                    size = int(attrs.get('size', 0))
                    result.append({'name': name, 'size': size})
                elif attrs.get('type') == 'dir':
                    pass
        except (ftplib.error_perm, AttributeError):
            try:
                names = ftp.nlst()
                for name in names:
                    if name not in ('.', '..'):
                        sz = 0
                        try:
                            sz = int(ftp.size(name))
                        except Exception:
                            sz = 0
                        result.append({'name': name, 'size': sz})
            except ftplib.error_perm:
                lines = []
                ftp.dir(lines.append)
                for line in lines:
                    parts = line.split(None, 8)
                    if len(parts) >= 9 and not parts[8].startswith('.'):
                        result.append({'name': parts[8], 'size': 0})
    finally:
        try:
            ftp.quit()
        except Exception as e:
            console_log('ERROR', f'FTP 断开清理失败: {e}')
    return result

def ftp_download(url, filename):
    info = parse_ftp_info(url)
    ftp = ftplib.FTP()
    ftp.connect(info['host'], info['port'], timeout=30)
    ftp.login(info['user'], info['password'])
    try:
        ftp.cwd(info['path'])
        buf = io.BytesIO()
        ftp.retrbinary('RETR ' + filename, buf.write)
        return buf.getvalue()
    finally:
        try:
            ftp.quit()
        except Exception as e:
            console_log('ERROR', f'FTP 断开清理失败: {e}')

def ftp_upload(url, filename, data):
    info = parse_ftp_info(url)
    ftp = ftplib.FTP()
    ftp.connect(info['host'], info['port'], timeout=60)
    ftp.login(info['user'], info['password'])
    try:
        ftp.cwd(info['path'])
        ftp.storbinary('STOR ' + filename, io.BytesIO(data))
    finally:
        try:
            ftp.quit()
        except Exception as e:
            console_log('ERROR', f'FTP 断开清理失败: {e}')

# ─── Directory listing parser (HTTP HTML) ────────────────────────────────────

def parse_html_listing(html):
    files = []
    pattern = re.compile(r'<a\s+href="([^"]*)"[^>]*>([^<]*)</a>([^\n]*)', re.IGNORECASE)
    for match in pattern.finditer(html):
        href = match.group(1).strip()
        text = match.group(2).strip()
        if href in ('../', './') or href.endswith('/') or href.startswith('?'):
            continue
        name = text or href
        ext = os.path.splitext(name)[1].lower()
        if ext in IMAGE_EXTS:
            size = 0
            size_matches = re.findall(
                r'(\d+(?:\.\d+)?)\s*(B|KB|MB|GB)\b',
                match.group(2) + match.group(3), re.IGNORECASE)
            if size_matches:
                num = float(size_matches[-1][0])
                unit = size_matches[-1][1].upper()
                multiplier = {'B': 1, 'KB': 1024, 'MB': 1048576, 'GB': 1073741824}[unit]
                size = int(round(num * multiplier))
            files.append({'name': name, 'size': size})
    return files

# ─── Local directory scanner ─────────────────────────────────────────────────

def local_list(path):
    """扫描本地目录，返回文件列表"""
    path = strip_file_prefix(path)
    files = []
    try:
        for root, dirs, filenames in os.walk(path):
            for name in filenames:
                ext = os.path.splitext(name)[1].lower()
                if ext in IMAGE_EXTS:
                    full = os.path.join(root, name)
                    try:
                        size = os.path.getsize(full)
                    except Exception as e:
                        console_log('ERROR', f'读取文件大小失败: {full} - {e}')
                        size = 0
                    # 相对于扫描目录的路径
                    rel = os.path.relpath(full, path)
                    files.append({'name': rel, 'size': size})
    except Exception as e:
        console_log('ERROR', f'本地扫描失败: {path} - {e}')
        raise
    return files

# ─── HTTP Request Handler ────────────────────────────────────────────────────

def _read_remote_file(url, filename):
    """通用远程文件读取，支持 HTTP、FTP、本地路径"""
    filename = _sanitize_rel_path(filename)
    if is_local_path(url):
        base = strip_file_prefix(url)
        _check_local_base(base)
        full = os.path.join(base, filename)
        _check_realpath_within(base, full)
        with open(full, 'rb') as f:
            return f.read()
    elif is_ftp(url):
        return ftp_download(url, filename)
    else:
        file_url = resolve_url(url, filename)
        return http_download(file_url)
