"""跨进程文件锁工具：Web 与 MCP 多进程写同一产物目录时串行化。

fcntl.flock 提供 POSIX 跨进程排它锁；Windows 无 fcntl 时回退为线程锁
（单进程语义），与仓库其余回退策略一致。
"""

from __future__ import annotations

import contextlib
import threading
from pathlib import Path
from typing import Iterator

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows 回退
    fcntl = None

# 每个锁文件一把线程锁：线程锁保证同进程内线程串行，fcntl 保证跨进程串行。
_locks: dict[str, threading.Lock] = {}
_registry_lock = threading.Lock()


@contextlib.contextmanager
def file_lock(lock_path: Path) -> Iterator[None]:
    """持有 lock_path 对应文件的排它锁（线程内 + 跨进程）。

    锁文件数量极小（每个服务目录一个 .lock），注册表无界增长风险可忽略。
    """

    lock_path = lock_path.expanduser().resolve()
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with _registry_lock:
        thread_lock = _locks.setdefault(str(lock_path), threading.Lock())
    with thread_lock:
        handle = lock_path.open("a+")
        try:
            if fcntl is not None:
                fcntl.flock(handle, fcntl.LOCK_EX)
            yield
        finally:
            if fcntl is not None:
                fcntl.flock(handle, fcntl.LOCK_UN)
            handle.close()
