# logging_util.py — 从 server.py 原样移出的日志工具（Console logging 区段），见 server.py 引用处

import collections
import itertools
import threading
import datetime
import sys
import platform
import ctypes

# ─── Console logging ─────────────────────────────────────────────────────────

LOG_COLORS = {
    'SCAN': '\033[96m',    # cyan
    'HASH': '\033[93m',    # yellow
    'SYNC': '\033[94m',    # blue
    'IMAGE': '\033[90m',   # grey
    'DONE': '\033[92m',    # green
    'ERROR': '\033[91m',   # red
    'BLACKLIST': '\033[95m',
}
RESET = '\033[0m'

# ─── 内存日志环形缓冲（供网页日志面板轮询）─────────────────────────────────
LOG_BUFFER = collections.deque(maxlen=500)
LOG_SEQ = itertools.count(1)   # 单调 id; 进程存活期内不回退, 清空不重置
LOG_LAST_ID = 0                # 已发出的最大 id（itertools.count 不可回读, 单独维护）
LOG_LOCK = threading.Lock()

# 检测终端是否支持 ANSI 颜色（Windows 旧终端可能不支持）
_USE_COLOR = True
if platform.system() == 'Windows':
    try:
        k32 = ctypes.windll.kernel32
        h = k32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_uint32()
        if k32.GetConsoleMode(h, ctypes.byref(mode)):
            k32.SetConsoleMode(h, mode.value | 0x0004)  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
    except Exception:
        ver = platform.version().split('.')
        _USE_COLOR = False if ver and int(ver[0]) < 10 else _USE_COLOR

def console_log(category, message):
    ts = datetime.datetime.now().strftime('%H:%M:%S')
    line = f'[{ts}] [{category}] {message}'

    # 写控制台 stderr（比 stdout 更可靠，在 PyInstaller 下也不会被吞）
    try:
        if _USE_COLOR:
            color = LOG_COLORS.get(category, '')
            sys.stderr.write(f' {color}{line}{RESET}\n')
        else:
            sys.stderr.write(f' {line}\n')
        sys.stderr.flush()
    except Exception: pass

    # 写内存环形缓冲（供网页日志面板增量轮询）; 存原始分类与消息, 不含 ANSI
    try:
        global LOG_LAST_ID
        with LOG_LOCK:
            # 取号必须在锁内: 与入队/LAST_ID 原子化, 否则并发乱序插入会让网页轮询按 id 过滤时静默跳行
            log_id = next(LOG_SEQ)
            LOG_LAST_ID = log_id
            LOG_BUFFER.append((log_id, ts, category, message))
    except Exception: pass
