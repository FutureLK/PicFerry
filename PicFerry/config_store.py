# config_store.py — 从 server.py 原样移出的配置存储（Config 区段），见 server.py 引用处

import os
import sys
import threading
import time
import configparser
from logging_util import console_log

# ─── Config ──────────────────────────────────────────────────────────────────

# 注意: 必须在【模块级】捕获脚本目录 —— 函数体内 dir() 只返回局部作用域,
# 看不到模块级 __file__, 因此不能在 runtime_dir() 内部判断 '__file__' in dir()。
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__)) if '__file__' in dir() else os.getcwd()

def runtime_dir():
    """EXE 模式下返回 EXE 所在目录, 源码模式返回 server.py 所在目录"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return _SCRIPT_DIR

def _prepare_config_dir():
    """确定并创建运行时 config/ 目录。
    优先程序旁 config/; 所在位置只读(如 EXE 被放进 Program Files)时降级到
    用户数据目录 %APPDATA%\\PicFerry\\config 并在 stderr 明示
    (console_log 此时尚未定义)。不兜底将使未捕获异常让进程在打印首行日志前闪退。"""
    primary = os.path.join(runtime_dir(), 'config')
    try:
        os.makedirs(primary, exist_ok=True)
        return primary
    except OSError as e:
        sys.stderr.write(f'警告: 无法在程序旁创建 config/ 目录({e})，已改用用户数据目录\n')
        sys.stderr.flush()
    base = os.environ.get('APPDATA') or os.path.expanduser('~')
    fallback = os.path.join(base, 'PicFerry', 'config')
    # 连用户目录都不可写属于环境级故障, 让异常带完整上下文自然抛出
    os.makedirs(fallback, exist_ok=True)
    return fallback

# 运行时文件统一收进 config/ 子目录; 旧版散落在程序根目录的文件首次启动自动挪入
CONFIG_DIR = _prepare_config_dir()

def _migrate_legacy_file(name):
    """旧版运行时文件在程序根目录; 首次启动自动挪进 config/。
    新位置已存在时以 config/ 为准, 旧文件保留不动; 失败静默(下次启动重试)。"""
    old = os.path.join(runtime_dir(), name)
    new = os.path.join(CONFIG_DIR, name)
    if os.path.exists(old) and not os.path.exists(new):
        try:
            os.replace(old, new)
        except OSError:
            pass   # 此处早于 console_log 定义, 静默即可

for _legacy_name in ('config.ini', 'blacklist.csv'):
    _migrate_legacy_file(_legacy_name)

CONFIG_PATH = os.path.join(CONFIG_DIR, 'config.ini')

# 新设置键: 默认值与范围 (key: (default, lo, hi, type))
_CONFIG_KEYS = {
    'thumbnailSize':  (48,   16,    128,    'int'),    # px
    'previewDelay':   (500,  100,   2000,   'int'),    # ms
    'pixivInterval':  (0.8,  0.1,   10,     'float'),  # s
    'pixivLimit':     (0,    0,     100000, 'int'),    # 0=全部
    'maxRows':        (1000, 10,    5000,   'int'),    # 行数上限
    'allowLan': (0, 0, 1, 'bool'),    # 0=仅本机 1=局域网
    'lightTheme': (0, 0, 1, 'bool'),  # 0=深色(默认) 1=浅色(日间模式)
    'debugMode': (0, 0, 1, 'bool'),   # 0=关闭(默认) 1=Debug诊断([DEBUG]耗时条目)
}

def _parse_config_value(key, raw):
    """解析配置值: 空串/非数字回落默认值, 越界钳制; 返回规范类型"""
    default, lo, hi, vtype = _CONFIG_KEYS[key]
    try:
        if vtype == 'bool':
            return str(raw).strip().lower() in ('1', 'true', 'yes', 'on')
        if vtype == 'float':
            val = float(str(raw).strip())
        else:
            val = int(float(str(raw).strip()))
        return max(lo, min(hi, val))
    # OverflowError: '1e400' 等 float() 得 inf 后 int(inf) 抛出; nan 由 ValueError 覆盖
    except (TypeError, ValueError, OverflowError):
        return default

# 配置读写共用一把锁: 本进程内读/写串行化, 从根上消除"replace 撞上打开中的句柄";
# 写端另备短退避重试, 兜住杀软扫描等【外部】进程的瞬时占用。
# 注意锁不可重入: 持锁区内不得再调用 load_config()/save_config()
_CONFIG_LOCK = threading.Lock()

def _parse_config_file():
    """解析 config.ini, 返回 (cfg|None, 错误文本)。
    整文件一次读入内存再解析(句柄只握一瞬间, 尽量避开写入方的 os.replace);
    缺失/不可读 → 空解析器(等同全默认, 首次启动的正常态);
    存在但无法解析(语法损坏/BOM/坏编码) → None, 由调用方决定回落还是拒绝覆盖。
    解析中途出错时已读入的半截内容作废, 一律按损坏处理。"""
    try:
        with open(CONFIG_PATH, 'rb') as f:
            raw = f.read()
    except OSError:
        return configparser.ConfigParser(), ''
    cfg = configparser.ConfigParser()
    try:
        cfg.read_string(raw.decode('utf-8'))
    except (configparser.Error, UnicodeDecodeError) as e:
        return None, str(e)
    return cfg, ''

def _conf_from_cfg(cfg):
    """从解析器抽取完整配置字典: 字符串键缺省 '', 数值键过注册表钳制"""
    conf = {
        'dev1ceA': cfg.get('Settings', 'dev1ceA', fallback=''),
        'dev1ceB': cfg.get('Settings', 'dev1ceB', fallback=''),
        'PixivUID': cfg.get('Settings', 'PixivUID', fallback=''),
        'PHPSESSID': cfg.get('Settings', 'PHPSESSID', fallback=''),
        'PixivL': cfg.get('Settings', 'PixivL', fallback=''),
    }
    for key in _CONFIG_KEYS:
        conf[key] = _parse_config_value(key, cfg.get('Settings', key, fallback=''))
    return conf

def load_config():
    """读取配置; 解析失败(损坏/缺段/BOM/坏编码)时回落全默认值, 不抛出"""
    with _CONFIG_LOCK:
        cfg, err = _parse_config_file()
    if cfg is None:
        console_log('ERROR', f'配置读取失败，使用默认值: {err}')
        cfg = configparser.ConfigParser()   # 空解析器 → 抽取结果即全默认值
    return _conf_from_cfg(cfg)

def save_config(data: dict):
    """原子写(临时文件 + os.replace)。文件已损坏时【拒绝】覆盖保存并返回 False——
    防止读到坏文件后的空默认值(PHPSESSID='')被整份写回、静默销毁用户凭证;
    其余场景返回是否成功"""
    with _CONFIG_LOCK:
        cfg, _ = _parse_config_file()
        if cfg is None:
            console_log('ERROR', '配置文件损坏，已拒绝自动保存（防凭证被默认值抹除）；请手工修复或删除该文件后重试')
            return False
        current = _conf_from_cfg(cfg)
        keys = ['dev1ceA', 'dev1ceB', 'PixivUID', 'PHPSESSID', 'PixivL'] + list(_CONFIG_KEYS.keys())
        lines = ['[Settings]\n']
        for k in keys:
            if k not in data:
                v = current.get(k, '')
            elif k in _CONFIG_KEYS:
                default, _, _, _ = _CONFIG_KEYS[k]
                v = _parse_config_value(k, data.get(k, default))
            else:
                v = data.get(k, '')
            if k in _CONFIG_KEYS and _CONFIG_KEYS[k][3] == 'bool':
                v = 1 if v else 0
            lines.append(f'{k} = {v}\n')
        tmp = CONFIG_PATH + '.tmp'
        # 读侧可能正短暂握着目标句柄, Windows 下 replace 会抛 WinError 5/32 → 快速退避重试
        last_err = None
        for attempt in range(5):
            try:
                with open(tmp, 'w', encoding='utf-8') as f:
                    f.writelines(lines)
                os.replace(tmp, CONFIG_PATH)
                return True
            except OSError as e:
                last_err = e
                time.sleep(0.004 * (attempt + 1))
        console_log('ERROR', f'配置写入失败(重试 5 次): {last_err}')
        try:
            os.remove(tmp)
        except OSError:
            pass
        return False
