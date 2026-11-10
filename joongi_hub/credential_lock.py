"""Reentrant OS file lock for credentials shared by independent stdio processes."""

import os
import threading
import time
from pathlib import Path

from joongi_hub.errors import RpcError


class CredentialLock:
    def __init__(self, path):
        self.path = Path(path)
        self.thread_lock = threading.RLock()
        self.local = threading.local()

    def __enter__(self):
        self.thread_lock.acquire()
        depth = getattr(self.local, "depth", 0)
        if depth:
            self.local.depth = depth + 1
            return self
        descriptor = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            if self.path.is_symlink() or self.path.parent.is_symlink():
                raise RpcError(-32040, "인증 잠금 경로의 symlink는 지원하지 않습니다.")
            descriptor = os.open(
                self.path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600
            )
            deadline = time.monotonic() + 30
            while True:
                try:
                    if os.name == "nt":
                        import msvcrt

                        os.lseek(descriptor, 0, os.SEEK_SET)
                        msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl

                        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError as exc:
                    if time.monotonic() >= deadline:
                        raise RpcError(
                            -32040, "다른 프로세스가 인증을 갱신 중입니다. 잠시 후 다시 시도하세요."
                        ) from exc
                    time.sleep(0.025)
            if os.fstat(descriptor).st_size == 0:
                os.write(descriptor, b"\0")
            self.local.descriptor = descriptor
            self.local.depth = 1
            return self
        except BaseException:
            if descriptor is not None:
                os.close(descriptor)
            self.thread_lock.release()
            raise

    def __exit__(self, *args):
        self.local.depth -= 1
        try:
            if not self.local.depth:
                descriptor = self.local.descriptor
                try:
                    if os.name == "nt":
                        import msvcrt

                        os.lseek(descriptor, 0, os.SEEK_SET)
                        msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
                    else:
                        import fcntl

                        fcntl.flock(descriptor, fcntl.LOCK_UN)
                finally:
                    os.close(descriptor)
        finally:
            self.thread_lock.release()
