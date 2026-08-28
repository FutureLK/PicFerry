# pathsafety.py — 从 server.py 原样移出的本地路径安全函数（路径净化与三层防线校验），见 server.py 引用处

import os
import re
from config_store import load_config

def is_local_path(path):
    """检测是否为本地磁盘路径"""
    if path.lower().startswith('file:///'):
        return True
    if path.lower().startswith('file:'):
        return True
    if re.match(r'^[a-zA-Z]:[\\/]', path):
        return True
    return False

def strip_file_prefix(path):
    """去掉 file:/// 前缀"""
    if path.lower().startswith('file:///'):
        return path[8:]  # file:///C:/ → C:/
    if path.lower().startswith('file://'):
        return path[7:]
    if path.lower().startswith('file:'):
        p = path[5:]
        if len(p) >= 3 and p[0] in '/\\' and p[1:2].isalpha() and p[2] == ':':
            p = p[1:]
        return p
    return path

# ─── 本地路径参数净化 (H2c) ─────────────────────────────────────────────────

def _safe_error_text(e):
    """脱敏错误文案: 剥离引号包裹的本地/UNC/file: 路径（防布局泄露），保留异常原因，截断 120 字符"""
    s = str(e)
    s = re.sub(r"file:(//)?/?", '', s, flags=re.IGNORECASE)          # 先剥 file: 前缀（覆盖 file:///、file://、file:/）
    s = re.sub(r"[\"'](([A-Za-z]:[\\/])|(\\\\|//))[^\"']*[\"']", '<路径>', s)
    return s[:120]

def _sanitize_rel_path(name):
    """拒绝绝对路径、盘符、`..` 组件、尾部空格/点的组件、Windows 保留设备名、
    控制字符（\\r\\n 等防 FTP 拼接命令注入）、冒号（NTFS ADS 流语法; 盘符检查
    已在前, 此处的冒号只会是流分隔符）; 允许相对子目录（local_list 产出 rel 路径）"""
    if not isinstance(name, str) or not name:
        raise ValueError('非法文件名')
    if os.path.isabs(name) or re.match(r'^[a-zA-Z]:', name):
        raise ValueError('非法文件名')
    if re.search(r'[\x00-\x1f]', name):
        raise ValueError('非法文件名')
    if ':' in name:
        raise ValueError('非法文件名')
    _reserved = {'CON', 'PRN', 'AUX', 'NUL'} | {f'COM{i}' for i in range(1, 10)} | {f'LPT{i}' for i in range(1, 10)}
    for part in name.replace('\\', '/').split('/'):
        if part == '..' or part.rstrip(' .') == '..':
            raise ValueError('非法文件名')
        if part != part.rstrip(' .'):
            raise ValueError('非法文件名')          # Win32 去尾空格/点 → 路径规范化绕过
        if part.split('.', 1)[0].rstrip(' .').upper() in _reserved:
            raise ValueError('非法文件名')          # NUL/CON/COM1 等设备名（rstrip 先剥尾空格/点，防 `con .txt` 穿透）
    return name

def _declared_local_bases():
    """config 声明的本地路径基座（dev1ceA/dev1ceB/PixivL 中属于本地路径者）; normcase+realpath 规范化"""
    conf = load_config()
    bases = []
    for key in ('dev1ceA', 'dev1ceB', 'PixivL'):
        p = conf.get(key, '')
        if p and is_local_path(p):
            bases.append(os.path.realpath(os.path.normcase(os.path.normpath(strip_file_prefix(p)))))
    return bases

def _check_local_base(base):
    """本地读/写基座必须位于 config 声明设备路径之下（防 url/from/to 不受限的任意文件读写链）;
    normcase 处理 Windows 大小写不敏感; realpath 处理 junction/symlink 逃逸"""
    b = os.path.realpath(os.path.normcase(os.path.normpath(base)))
    for declared in _declared_local_bases():
        if b == declared or b.startswith(declared + os.sep):
            return
    raise ValueError('未声明的本地路径')

def _check_realpath_within(base, full):
    """最终读写路径的 realpath 必须仍在声明基座内（防基座内 junction 指向外部后越界读写）;
    normcase 与 _check_local_base 口径一致（Windows 大小写不敏感）"""
    rb = os.path.realpath(os.path.normcase(os.path.normpath(base)))
    # 两侧都必须走同一"先解析后比较"管线(realpath 输出磁盘规范大小写),
    # 此处【勿】对 rf 单独补 normcase——顺序不同会让一侧规范一侧小写,
    # FUTURE~1 类短名目录下正当路径被误判越界(实测复盘结论)
    rf = os.path.realpath(full)
    if rf != rb and not rf.startswith(rb + os.sep):
        raise ValueError('路径越出声明基座')

def _assert_declared_scan_base(url):
    """目录扫描的本地基座校验: 列目录同属读取行为, 与 _read_remote_file 读链路
    同受三层防线约束 —— 本地路径必须位于 config 已声明的基座之内; 网络形态放行。
    未声明时抛 ValueError('未声明的本地路径') 由调用方统一处理。"""
    if is_local_path(url):
        _check_local_base(strip_file_prefix(url))
