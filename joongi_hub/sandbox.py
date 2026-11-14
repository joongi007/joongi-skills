"""Fail-closed execution boundary for registered stdio MCP programs."""

import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

from joongi_hub.errors import RpcError

NATIVE_IMAGE = "debian@sha256:734a72b3d6142a71993b4bc580ca01d8ca687f77a2c422d96a961d3376b179bc"

SAFE_ENV = {
    "PATH",
    "SYSTEMROOT",
    "WINDIR",
    "USERPROFILE",
    "APPDATA",
    "LOCALAPPDATA",
    "TEMP",
    "TMP",
    "TMPDIR",
    "LANG",
    "LC_ALL",
    "HOME",
}


def validate_sandbox(value):
    if not isinstance(value, dict) or set(value) - {
        "backend",
        "read",
        "write",
        "image",
        "mounts",
        "memory_mb",
        "cpu_seconds",
        "process_backend",
    }:
        raise RpcError(-32602, "샌드박스 설정 필드를 확인하세요.")
    if value.get("backend", "auto") not in {
        "auto",
        "landlock",
        "docker",
        "docker-native",
        "first-party-graph",
    }:
        raise RpcError(-32602, "지원하지 않는 샌드박스입니다. 제한 없는 실행은 지원하지 않습니다.")
    if value.get("process_backend", "docker-native") not in {"auto", "landlock", "docker-native"}:
        raise RpcError(-32602, "코드 그래프 process backend를 확인하세요.")
    for key in ("read", "write"):
        paths = value.get(key, [])
        if (
            not isinstance(paths, list)
            or len(paths) > 32
            or not all(isinstance(p, str) and Path(p).is_absolute() for p in paths)
        ):
            raise RpcError(-32602, "샌드박스 경로는 절대 경로 배열로 지정하세요.")
    for key, default, maximum in (("memory_mb", 1024, 4096), ("cpu_seconds", 120, 600)):
        number = value.get(key, default)
        if type(number) is not int or not 1 <= number <= maximum:
            raise RpcError(-32602, "샌드박스 자원 제한을 확인하세요.")
    if value.get("backend") == "docker":
        if not isinstance(value.get("image"), str) or not re.fullmatch(
            r"[a-zA-Z0-9./:_-]+@sha256:[a-f0-9]{64}", value["image"]
        ):
            raise RpcError(-32602, "Docker 이미지는 검토한 sha256 digest로 고정하세요.")
        mounts = value.get("mounts", [])
        if not isinstance(mounts, list) or len(mounts) > 32:
            raise RpcError(-32602, "Docker mount 목록을 확인하세요.")
        for mount in mounts:
            if (
                not isinstance(mount, dict)
                or set(mount) != {"source", "target", "write"}
                or not isinstance(mount["source"], str)
                or not Path(mount["source"]).is_absolute()
                or not isinstance(mount["target"], str)
                or type(mount["write"]) is not bool
            ):
                raise RpcError(-32602, "Docker mount의 source·target·write를 지정하세요.")
            target = mount["target"]
            if (
                not target.startswith("/workspace/")
                or ".." in Path(target).parts
                or any(c in target + mount["source"] for c in ",\r\n")
            ):
                raise RpcError(-32602, "Docker mount는 /workspace/ 아래에만 지정하세요.")


def _grant(path, write=False, state=None):
    path = Path(path).expanduser().resolve()
    home = Path.home().resolve()
    protected = [
        home / p
        for p in (
            ".ssh",
            ".aws",
            ".gnupg",
            ".config",
            ".codex",
            ".claude",
            ".local/share/keyrings",
            "Library/Keychains",
        )
    ]
    for root in {home / ".local/share/joongi-hub", *([Path(state).resolve()] if state else [])}:
        protected += [
            root / p
            for p in (
                "auth",
                "http-auth.json",
                "servers.json",
                "backups",
                "approvals.sqlite3",
                "tasks.sqlite3",
                "security-events.jsonl",
                "security-events.previous.jsonl",
            )
        ]
    if write:
        protected += [
            Path(__file__).parent.parent.resolve(),
            Path(sys.prefix).resolve(),
            Path(sys.base_prefix).resolve(),
        ]
    if any(
        path == base or base in path.parents
        for base in (Path("/proc"), Path("/sys"), Path("/dev"), Path("/run"))
    ):
        raise RpcError(-32046, "OS 실행 상태·장치·서비스 소켓은 공유할 수 없습니다.")
    if path in {
        Path(path.anchor),
        home,
        Path("/tmp"),
        Path("/var"),
        Path("/var/tmp"),
        Path("/etc"),
        Path("/proc"),
        Path("/sys"),
        Path("/dev"),
        Path("/run"),
    } or any(path == p or path in p.parents or p in path.parents for p in protected):
        raise RpcError(
            -32046, "OS·Hub 자격증명 또는 신뢰한 실행 코드를 포함하는 경로는 허용하지 않습니다."
        )
    if write and not path.exists():
        path.mkdir(parents=True, mode=0o700)
    if not path.exists() or not (path.is_file() or path.is_dir()):
        raise RpcError(-32046, "샌드박스 경로는 존재하는 파일 또는 디렉터리여야 합니다.")
    return str(path)


def _entry_script(config):
    for arg in config.get("args", []):
        if arg in {"-c", "-m", "-e", "--eval"}:
            return None
        if arg.startswith("-"):
            continue
        return arg if len(arg) <= 4096 and Path(arg).is_absolute() and Path(arg).is_file() else None
    return None


def _helper_environment():
    return {k: v for k, v in os.environ.items() if k.upper() in SAFE_ENV}


def status():
    native = False
    if sys.platform == "linux":
        from joongi_hub.linux_sandbox import supported

        native = supported()
    engine = shutil.which("docker")
    image_ready = False
    if engine:
        try:
            image_ready = (
                subprocess.run(
                    [engine, "image", "inspect", NATIVE_IMAGE],
                    capture_output=True,
                    timeout=5,
                    env=_helper_environment(),
                ).returncode
                == 0
            )
        except (OSError, subprocess.TimeoutExpired):
            pass
    return {
        "required": True,
        "landlock_supported": native,
        "docker_available": bool(engine),
        "native_image_ready": image_ready,
        "native_image": NATIVE_IMAGE,
        "network": "none",
        "unrestricted_fallback": False,
    }


def prepare():
    engine = shutil.which("docker")
    if not engine:
        raise RpcError(-32046, "Docker Engine을 준비하거나 Linux/WSL 실행 환경을 선택하세요.")
    try:
        result = subprocess.run(
            [engine, "pull", NATIVE_IMAGE],
            capture_output=True,
            timeout=180,
            env=_helper_environment(),
        )
        if result.returncode:
            raise RpcError(-32046, "고정된 격리 이미지를 준비하지 못했습니다.")
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RpcError(
            -32046, "Docker 준비가 실패했습니다. 일반 실행으로 우회하지 않습니다."
        ) from exc
    return status()


class Execution:
    def __init__(self, config, environment, state=None):
        self.directory = tempfile.TemporaryDirectory(
            prefix="joongi-mcp-sandbox-", dir=Path.home() if os.name == "nt" else None
        )
        self.container = None
        self.engine = None
        self.environment = _helper_environment()
        try:
            settings = config.get("sandbox", {})
            validate_sandbox(settings)
            backend = settings.get("backend", "auto")
            if backend == "first-party-graph":
                from joongi_hub.review_graph import trusted_adapter

                if not trusted_adapter(config):
                    raise RpcError(-32046, "첫 번째 파티 adapter의 명령·권한이 일치하지 않습니다.")
                for granted in settings.get("read", []):
                    _grant(granted, state=state)
                for granted in settings.get("write", []):
                    _grant(granted, write=True, state=state)
                self.command = [config["command"], *config.get("args", [])]
                self.environment = _helper_environment()
                return
            windows_paths = [
                *settings.get("read", []),
                *settings.get("write", []),
                *config.get("args", []),
            ]
            drvfs = any(
                isinstance(p, str) and re.match(r"^/mnt/[a-zA-Z]/", p) for p in windows_paths
            )
            if backend == "auto" and sys.platform == "linux" and not drvfs:
                from joongi_hub.linux_sandbox import supported

                if not supported() or os.geteuid() == 0:
                    backend = "docker-native"
            if (
                backend == "docker"
                or backend == "docker-native"
                or (backend == "auto" and sys.platform == "linux" and drvfs)
            ):
                if backend != "docker":
                    settings = self._native_mounts(config, settings, state)
                self._docker(config, environment, settings, state, native=backend != "docker")
                return
            if sys.platform != "linux":
                raise RpcError(
                    -32046,
                    "stdio MCP에는 WSL/Linux 또는 Docker 샌드박스가 필요합니다.",
                )
            from joongi_hub.linux_sandbox import supported

            if not supported() or os.geteuid() == 0:
                raise RpcError(
                    -32046,
                    "Landlock ABI 6+·libseccomp가 필요합니다. 격리 없는 실행을 차단했습니다.",
                )
            program = shutil.which(config["command"], path=environment.get("PATH"))
            if not program:
                raise RpcError(-32046, "MCP 실행 파일을 찾을 수 없습니다.")
            program = str(Path(program).absolute())
            scratch = Path(self.directory.name) / "scratch"
            scratch.mkdir(mode=0o700)
            reads = [
                str(Path(p).resolve())
                for p in (
                    "/usr",
                    "/bin",
                    "/sbin",
                    "/lib",
                    "/lib64",
                    "/etc/ld.so.cache",
                    "/dev/urandom",
                    "/dev/random",
                )
                if Path(p).exists()
            ]
            reads.extend([str(Path(__file__).parent.resolve()), str(Path(program).resolve())])
            assets = Path(__file__).parent.parent / "examples/apps"
            if assets.is_dir():
                reads.append(str(assets.resolve()))
            for prefix in {
                Path(sys.prefix),
                Path(program).parent.parent,
                Path(program).resolve().parent.parent,
            }:
                if (prefix / "pyvenv.cfg").is_file() or (prefix / "lib").is_dir():
                    reads.append(str(prefix.resolve()))
            entry = _entry_script(config)
            if entry:
                reads.append(_grant(entry, state=state))
            reads += [_grant(p, state=state) for p in settings.get("read", [])]
            writes = [
                str(scratch),
                *[_grant(p, write=True, state=state) for p in settings.get("write", [])],
            ]
            policy = {
                "read": sorted(set(reads)),
                "write": sorted(set(writes)),
                "scratch": str(scratch),
                "command": [program, *config.get("args", [])],
                "environment": environment,
                "memory_mb": settings.get("memory_mb", 1024),
                "cpu_seconds": settings.get("cpu_seconds", 120),
            }
            policy_path = Path(self.directory.name) / "policy.json"
            policy_path.write_text(json.dumps(policy), encoding="utf-8")
            policy_path.chmod(0o600)
            source = Path(__file__).resolve().parent.parent
            bootstrap = (
                f"import runpy,sys;sys.path.insert(0,{str(source)!r});"
                "runpy.run_module('joongi_hub.sandbox_exec',run_name='__main__')"
            )
            self.command = [sys.executable, "-I", "-B", "-c", bootstrap, str(policy_path)]
        except Exception:
            self.directory.cleanup()
            raise

    def _native_mounts(self, config, settings, state):
        if sys.platform != "linux":
            raise RpcError(-32046, "Host runtime 샌드박스는 Linux/WSL에서 실행하세요.")
        program = shutil.which(config["command"])
        if not program:
            raise RpcError(-32046, "MCP 실행 파일을 찾을 수 없습니다.")
        program = str(Path(program).absolute())
        reads = ["/usr", str(Path(__file__).parent.resolve())]
        assets = Path(__file__).parent.parent / "examples/apps"
        if assets.is_dir():
            reads.append(str(assets.resolve()))
        for prefix in {
            Path(sys.prefix),
            Path(program).parent.parent,
            Path(program).resolve().parent.parent,
        }:
            if prefix != Path("/") and (
                (prefix / "pyvenv.cfg").is_file() or (prefix / "lib").is_dir()
            ):
                reads.append(str(prefix.resolve()))
        entry = _entry_script(config)
        if entry:
            reads.append(_grant(entry, state=state))
        reads += [_grant(p, state=state) for p in settings.get("read", [])]
        writes = [_grant(p, write=True, state=state) for p in settings.get("write", [])]
        mounts = [
            {"source": p, "target": p, "write": False}
            for p in sorted(set(reads))
            if p not in writes
        ]
        mounts += [{"source": p, "target": p, "write": True} for p in writes]
        # Program is resolved outside the container, without allowing a shell.
        self.native_program = program
        return {**settings, "image": NATIVE_IMAGE, "mounts": mounts}

    def _docker(self, config, environment, settings, state, native=False):
        engine = shutil.which("docker")
        if not engine:
            raise RpcError(
                -32046, "Docker 샌드박스를 사용할 수 없습니다. 일반 실행으로 우회하지 않습니다."
            )
        try:
            checked = subprocess.run(
                [engine, "info", "--format", "{{json .}}"],
                capture_output=True,
                timeout=8,
                env=_helper_environment(),
            )
            info = json.loads(checked.stdout) if checked.returncode == 0 else {}
            options = info.get("SecurityOptions", [])
            if not all(
                info.get(key) is True for key in ("MemoryLimit", "PidsLimit", "CpuCfsQuota")
            ):
                raise ValueError
            if not any(
                option in {"name=seccomp,profile=builtin", "name=seccomp,profile=default"}
                for option in options
            ):
                raise ValueError
        except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
            raise RpcError(
                -32046, "seccomp·메모리·PID·CPU 제한이 활성화된 Docker Engine이 필요합니다."
            ) from exc
        profile_source = Path(__file__).parent / "_vendor/docker_seccomp/default.json"
        profile_bytes = profile_source.read_bytes()
        if (
            hashlib.sha256(profile_bytes).hexdigest()
            != "3320527d4568265ac97a077609b1bfd4cfd0d789eeb9239b7e094b1526675406"
        ):
            raise RpcError(-32046, "신뢰한 Docker seccomp 프로필이 변경됐습니다.")
        profile = json.loads(profile_bytes)
        blocked = {"socket", "connect", "bind", "listen", "accept", "accept4"}
        for rule in profile["syscalls"]:
            if rule["action"] == "SCMP_ACT_ALLOW":
                rule["names"] = [name for name in rule["names"] if name not in blocked]
        profile["syscalls"] = [rule for rule in profile["syscalls"] if rule["names"]]
        # Private socketpairs are needed by asyncio; there is no connect endpoint.
        profile_path = Path(self.directory.name) / "docker-seccomp.json"
        profile_path.write_text(json.dumps(profile), encoding="utf-8")
        profile_path.chmod(0o600)
        self.engine = engine
        self.container = "joongi-mcp-" + Path(self.directory.name).name.rsplit("-", 1)[-1]
        uid = os.getuid() if hasattr(os, "getuid") and os.getuid() else 65534
        self.command = [
            engine,
            "run",
            "--rm",
            "--interactive",
            "--pull=never",
            "--name",
            self.container,
            "--network=none",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges:true",
            "--security-opt=seccomp=" + str(profile_path),
            "--pids-limit=64",
            "--memory=" + str(settings.get("memory_mb", 1024)) + "m",
            "--memory-swap=" + str(settings.get("memory_mb", 1024)) + "m",
            "--ulimit=cpu=" + str(settings.get("cpu_seconds", 120)),
            "--ulimit=nofile=256:256",
            "--ulimit=fsize=268435456:268435456",
            "--ulimit=core=0:0",
            "--cpus=1",
            "--user=" + str(uid) + ":" + str(uid),
            "--workdir=/sandbox",
            "--tmpfs=/tmp:rw,noexec,nosuid,size=64m",
            "--tmpfs=/sandbox:rw,noexec,nosuid,size=64m,mode=700,uid=" + str(uid),
        ]
        for mount in settings.get("mounts", []):
            source = mount["source"] if native else _grant(mount["source"], mount["write"], state)
            if any(c in source + mount["target"] for c in ",\r\n"):
                raise RpcError(-32046, "샌드박스 mount 경로에 구분자를 넣을 수 없습니다.")
            suffix = "" if mount["write"] else ",readonly"
            self.command += [
                "--mount",
                "type=bind,source=" + source + ",target=" + mount["target"] + suffix,
            ]
        env_file = Path(self.directory.name) / "environment"
        if any("\n" in k + v or "\r" in k + v or "=" in k for k, v in environment.items()):
            raise RpcError(-32046, "Docker 환경변수에는 줄바꿈을 넣을 수 없습니다.")
        env_file.write_text(
            "\n".join(k + "=" + v for k, v in environment.items())
            + "\nHOME=/sandbox\nTMPDIR=/tmp\n",
            encoding="utf-8",
        )
        env_file.chmod(0o600)
        self.command += [
            "--env-file",
            str(env_file),
            settings["image"],
            self.native_program if native else config["command"],
            *config.get("args", []),
        ]

    def cleanup(self, process=None):
        if process and os.name != "nt":
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
        if self.container:
            try:
                subprocess.run(
                    [self.engine, "rm", "--force", self.container],
                    capture_output=True,
                    timeout=10,
                    env=_helper_environment(),
                )
            except (OSError, subprocess.TimeoutExpired):
                pass
        self.directory.cleanup()
