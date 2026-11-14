"""Landlock ABI >= 6 and libseccomp enforcement in a fresh exec helper.

No application-controlled code runs before enforcement. There is no preexec_fn
in the multithreaded Hub and no fallback to an unrestricted child process.
"""

import ctypes
import errno
import os
import platform
import resource


class Ruleset(ctypes.Structure):
    _fields_ = [
        ("filesystem", ctypes.c_uint64),
        ("network", ctypes.c_uint64),
        ("scoped", ctypes.c_uint64),
    ]


class PathRule(ctypes.Structure):
    _pack_ = 1
    _fields_ = [("allowed", ctypes.c_uint64), ("descriptor", ctypes.c_int32)]


class Compare(ctypes.Structure):
    _fields_ = [
        ("argument", ctypes.c_uint),
        ("operator", ctypes.c_uint),
        ("a", ctypes.c_uint64),
        ("b", ctypes.c_uint64),
    ]


READ = 1 | 4 | 8
WRITE = 2 | 4 | 8 | 16 | 32 | 128 | 256 | 4096 | 8192 | 16384


def supported():
    if platform.system() != "Linux" or platform.machine().lower() not in {"x86_64", "aarch64"}:
        return False
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        ctypes.CDLL("libseccomp.so.2")
        return libc.syscall(444, 0, 0, 1) >= 6
    except OSError:
        return False


def enforce(policy):
    if not supported() or os.geteuid() == 0:
        raise RuntimeError("Landlock ABI 6+ and libseccomp are required")
    libc = ctypes.CDLL(None, use_errno=True)
    libc.prctl.argtypes = [
        ctypes.c_int,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_ulong,
    ]
    if libc.prctl(38, 1, 0, 0, 0):  # PR_SET_NO_NEW_PRIVS
        raise OSError(ctypes.get_errno(), "no_new_privs failed")
    rules = Ruleset(0xFFFF, 3, 3)  # All ABI 6 filesystem, TCP and scope restrictions.
    descriptor = libc.syscall(444, ctypes.byref(rules), ctypes.sizeof(rules), 0)
    if descriptor < 0:
        raise OSError(ctypes.get_errno(), "Landlock ruleset creation failed")
    try:
        for path, rights in [(p, READ) for p in policy["read"]] + [
            (p, WRITE) for p in policy["write"]
        ]:
            path_descriptor = os.open(path, os.O_PATH | os.O_CLOEXEC)
            try:
                if not os.path.isdir(path):
                    rights &= 1 | 2 | 4 | 16384
                    if not os.path.isfile(path):
                        rights &= 2 | 4
                rule = PathRule(rights, path_descriptor)
                if libc.syscall(445, descriptor, 1, ctypes.byref(rule), 0):
                    raise OSError(ctypes.get_errno(), "Landlock path rule failed")
            finally:
                os.close(path_descriptor)
        if libc.syscall(446, descriptor, 0):
            raise OSError(ctypes.get_errno(), "Landlock enforcement failed")
    finally:
        os.close(descriptor)
    # Load by fixed system soname; untrusted loader environment is not present.
    seccomp = ctypes.CDLL("libseccomp.so.2", use_errno=True)
    seccomp.seccomp_init.argtypes, seccomp.seccomp_init.restype = [ctypes.c_uint32], ctypes.c_void_p
    seccomp.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
    seccomp.seccomp_rule_add_array.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_int,
        ctypes.c_uint,
        ctypes.POINTER(Compare),
    ]
    seccomp.seccomp_load.argtypes = [ctypes.c_void_p]
    seccomp.seccomp_release.argtypes = [ctypes.c_void_p]
    context = seccomp.seccomp_init(
        0x7FFF0000
    )  # SCMP_ACT_ALLOW; native arch only, bad arches killed.
    if not context:
        raise RuntimeError("seccomp initialization failed")

    def deny(name, comparison=None, error=errno.EPERM):
        number = seccomp.seccomp_syscall_resolve_name(name.encode())
        if number < 0:
            return
        pointer = ctypes.byref(comparison) if comparison else None
        if seccomp.seccomp_rule_add_array(
            context, 0x00050000 | error, number, int(comparison is not None), pointer
        ):
            raise RuntimeError("seccomp rule could not be installed")

    try:
        for name in (
            "socket",
            "connect",
            "bind",
            "listen",
            "accept",
            "accept4",
            "ptrace",
            "process_vm_readv",
            "process_vm_writev",
            "pidfd_getfd",
            "pidfd_open",
            "mount",
            "umount2",
            "pivot_root",
            "chroot",
            "unshare",
            "setns",
            "bpf",
            "perf_event_open",
            "userfaultfd",
            "open_by_handle_at",
            "name_to_handle_at",
            "keyctl",
            "add_key",
            "request_key",
            "io_uring_setup",
            "io_uring_enter",
            "io_uring_register",
            "chmod",
            "fchmod",
            "fchmodat",
            "fchmodat2",
            "chown",
            "fchown",
            "lchown",
            "fchownat",
            "setxattr",
            "lsetxattr",
            "fsetxattr",
            "removexattr",
            "lremovexattr",
            "fremovexattr",
            "utime",
            "utimes",
            "utimensat",
            "futimesat",
            "setsid",
            "setpgid",
            "fork",
            "vfork",
        ):
            deny(name)
        # glibc can fall back from clone3 to clone for threads. Subprocesses are
        # unavailable in the native profile; use the Docker profile when needed.
        deny("socketpair", Compare(0, 1, 1, 0))  # only private AF_UNIX pairs
        deny("clone3", error=errno.ENOSYS)
        deny("clone", Compare(0, 7, 0x10000, 0))  # no CLONE_THREAD => deny
        for flag in (
            0x80,
            0x20000,
            0x2000000,
            0x4000000,
            0x8000000,
            0x10000000,
            0x20000000,
            0x40000000,
        ):
            deny("clone", Compare(0, 7, flag, flag))
        if seccomp.seccomp_load(context):
            raise RuntimeError("seccomp enforcement failed")
    finally:
        seccomp.seccomp_release(context)
    for kind, value in (
        (resource.RLIMIT_AS, policy["memory_mb"] * 1024**2),
        (resource.RLIMIT_CPU, policy["cpu_seconds"]),
        (resource.RLIMIT_FSIZE, 256 * 1024**2),
        (resource.RLIMIT_NOFILE, 256),
        (resource.RLIMIT_CORE, 0),
    ):
        soft, hard = resource.getrlimit(kind)
        limit = value if hard == resource.RLIM_INFINITY else min(value, hard)
        resource.setrlimit(kind, (limit, limit))
