"""Opt-in Playwright container profile; no general-purpose network permission."""

import hashlib
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

from joongi_hub.browser_proxy import EgressProxy, origins
from joongi_hub.errors import RpcError

MCP_VERSION = "0.0.86"
BASE_IMAGES = {
    "x86_64": "mcr.microsoft.com/playwright@sha256:"
    "f6fe3cf9a493670b9a20f33597a807262abb25c40c31839ba4ac1dbc51fe7366",
    "aarch64": "mcr.microsoft.com/playwright@sha256:"
    "714043ec4d54008d194a4b3835bc2a1156c51862d8bb45d72bea414f0ce9ed61",
}
FILES = Path(__file__).with_name("browser_container")


def validate_browser(settings):
    if set(settings) - {"backend", "image", "browser_origins", "browser_display", "memory_mb"}:
        raise RpcError(-32602, "브라우저에는 임의 mount·환경변수·실행 경로를 지정할 수 없습니다.")
    if not isinstance(settings.get("image"), str) or not re.fullmatch(
        r"sha256:[a-f0-9]{64}", settings["image"]
    ):
        raise RpcError(-32602, "준비한 로컬 브라우저 이미지의 sha256 ID를 지정하세요.")
    origins(settings.get("browser_origins"))
    if settings.get("browser_display", "headless") not in {"headless", "wayland"}:
        raise RpcError(-32602, "브라우저 화면은 headless 또는 명시적 wayland로 선택하세요.")


def engine_info():
    from joongi_hub.sandbox import _helper_environment

    engine = shutil.which("docker")
    if not engine or sys.platform != "linux":
        raise RpcError(-32046, "격리 브라우저에는 Linux/WSL과 Docker Engine이 필요합니다.")
    try:
        result = subprocess.run(
            [engine, "info", "--format", "{{json .}}"],
            env=_helper_environment(),
            capture_output=True,
            timeout=8,
            check=True,
        )
        info = json.loads(result.stdout)
        if not all(
            info.get(key) is True for key in ("MemoryLimit", "PidsLimit", "CpuCfsQuota")
        ) or not any(
            value in {"name=seccomp,profile=builtin", "name=seccomp,profile=default"}
            for value in info.get("SecurityOptions", [])
        ):
            raise ValueError
        return engine
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        raise RpcError(
            -32046, "seccomp·메모리·PID·CPU 제한이 활성화된 Docker가 필요합니다."
        ) from exc


def prepare():
    """Explicit build only. Connection never pulls an image or installs packages."""
    from joongi_hub.sandbox import _helper_environment

    engine = engine_info()
    base = BASE_IMAGES.get(platform.machine())
    if not base:
        raise RpcError(-32046, "브라우저 이미지는 Linux amd64/arm64만 지원합니다.")
    with tempfile.TemporaryDirectory(prefix="joongi-browser-build-") as temporary:
        target = Path(temporary)
        for name in ("entry.py", "package.json", "package-lock.json"):
            (target / name).write_bytes((FILES / name).read_bytes())
        (target / "Dockerfile").write_text(
            "FROM " + base + "\nWORKDIR /app\n"
            "COPY package*.json ./\n"
            "RUN npm ci --ignore-scripts --omit=dev --no-audit --no-fund "
            "&& npm cache clean --force\n"
            "RUN apt-get purge -y gstreamer1.0-plugins-bad libgstreamer-plugins-bad1.0-0 "
            "&& rm -rf /usr/lib/node_modules/npm /usr/bin/npm /usr/bin/npx\n"
            "COPY entry.py /app/entry.py\n"
            'ENTRYPOINT ["python3", "-I", "-B", "/app/entry.py"]\n'
        )
        result = subprocess.run(
            [engine, "build", "--iidfile", str(target / "image-id"), str(target)],
            env=_helper_environment(),
            stdout=sys.stderr,
            stderr=sys.stderr,
            timeout=900,
        )
        if result.returncode:
            raise RpcError(
                -32046, "브라우저 이미지 준비에 실패했습니다. 일반 실행으로 우회하지 않습니다."
            )
        return {
            "image": (target / "image-id").read_text().strip(),
            "mcp_version": MCP_VERSION,
            "base": base,
        }


class BrowserExecution:
    def __init__(self, config):
        from joongi_hub.sandbox import _helper_environment

        settings = config["sandbox"]
        validate_browser(settings)
        if (
            config.get("env")
            or config.get("headers")
            or config.get("auth", {}).get("type", "none") != "none"
        ):
            raise RpcError(
                -32046, "격리 브라우저에는 Hub 인증 정보나 환경변수를 전달할 수 없습니다."
            )
        if "policy" not in config or config["policy"].get("allowed_tools"):
            raise RpcError(-32046, "브라우저는 자동 허용 없이 호출 승인을 사용하세요.")
        self.engine = engine_info()
        self.environment = _helper_environment()
        if os.getuid() == 0:
            raise RpcError(-32046, "브라우저 Hub는 root가 아닌 사용자로 실행하세요.")
        try:
            subprocess.run(
                [self.engine, "image", "inspect", settings["image"]],
                env=self.environment,
                capture_output=True,
                timeout=8,
                check=True,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise RpcError(
                -32046, "준비한 브라우저 이미지가 없습니다. browser --prepare를 실행하세요."
            ) from exc
        self.directory = tempfile.TemporaryDirectory(prefix="joongi-browser-")
        self.proxy = None
        self.container = "joongi-browser-" + uuid.uuid4().hex
        try:
            directory = Path(self.directory.name)
            proxy_path = directory / "egress.sock"
            uid = os.getuid() or 65534
            display = settings.get("browser_display", "headless")
            mounts = [
                "--mount",
                "type=bind,source=" + str(proxy_path) + ",target=/egress.sock,readonly",
            ]
            display_env = []
            if display == "wayland":
                candidates = [
                    Path("/mnt/wslg/runtime-dir/wayland-0"),
                    Path(f"/run/user/{uid}/wayland-0"),
                ]
                socket_path = next(
                    (
                        p
                        for p in candidates
                        if p.exists() and stat.S_ISSOCK(p.stat().st_mode) and p.stat().st_uid == uid
                    ),
                    None,
                )
                if socket_path is None:
                    raise RpcError(
                        -32046,
                        "Wayland 화면을 찾지 못했습니다. headless로 자동 전환하지 않습니다.",
                    )
                mounts += [
                    "--mount",
                    "type=bind,source=" + str(socket_path) + ",target=/tmp/wayland-0,readonly",
                ]
                display_env = ["--env=XDG_RUNTIME_DIR=/tmp", "--env=WAYLAND_DISPLAY=wayland-0"]
            # Chromium's own user-namespace sandbox remains enabled inside Docker.
            # Add only Chromium's documented namespace syscalls to the pinned Docker profile.
            profile_path = Path(__file__).parent / "_vendor/docker_seccomp/default.json"
            data = profile_path.read_bytes()
            if (
                hashlib.sha256(data).hexdigest()
                != "3320527d4568265ac97a077609b1bfd4cfd0d789eeb9239b7e094b1526675406"
            ):
                raise RpcError(-32046, "고정 seccomp 정책이 변경됐습니다.")
            profile = json.loads(data)
            profile["syscalls"].append(
                {
                    "names": ["clone", "unshare", "setns", "chroot"],
                    "action": "SCMP_ACT_ALLOW",
                    "args": [],
                }
            )
            seccomp = directory / "seccomp.json"
            seccomp.write_text(json.dumps(profile))
            self.proxy = EgressProxy(proxy_path, settings["browser_origins"])
            self.command = [
                self.engine,
                "run",
                "--rm",
                "--interactive",
                "--init",
                "--pull=never",
                "--name",
                self.container,
                "--network=none",
                "--read-only",
                "--cap-drop=ALL",
                "--security-opt=no-new-privileges:true",
                "--security-opt=seccomp=" + str(seccomp),
                "--user=" + str(uid) + ":" + str(uid),
                "--pids-limit=256",
                "--memory=" + str(settings.get("memory_mb", 2048)) + "m",
                "--memory-swap=" + str(settings.get("memory_mb", 2048)) + "m",
                "--cpus=2",
                "--ulimit=core=0:0",
                "--ulimit=nofile=512:512",
                "--shm-size=128m",
                "--tmpfs=/tmp:rw,nosuid,size=256m,mode=1777",
                "--env=HOME=/tmp",
                "--env=TMPDIR=/tmp",
                *[
                    "--env=" + key + "="
                    for key in (
                        "HTTP_PROXY",
                        "HTTPS_PROXY",
                        "ALL_PROXY",
                        "NO_PROXY",
                        "http_proxy",
                        "https_proxy",
                        "all_proxy",
                        "no_proxy",
                    )
                ],
                "--env=JOONGI_BROWSER_DISPLAY=" + display,
                "--env=JOONGI_BROWSER_ORIGINS=" + json.dumps(origins(settings["browser_origins"])),
                *display_env,
                *mounts,
                settings["image"],
            ]
        except Exception:
            self.cleanup()
            raise

    def cleanup(self):
        try:
            subprocess.run(
                [self.engine, "rm", "--force", self.container],
                env=self.environment,
                capture_output=True,
                timeout=8,
            )
        except (OSError, subprocess.SubprocessError):
            pass
        if self.proxy:
            self.proxy.close()
            self.proxy = None
        self.directory.cleanup()


def server_config(image, allowed, display="headless"):
    from joongi_hub.upstream import validate_server

    return validate_server(
        {
            "id": "playwright",
            "name": "Playwright browser · 브라우저 화면 클릭 입력 screenshot",
            "transport": "stdio",
            "command": "joongi-browser",
            "args": [],
            "enabled": True,
            "protocol_version": "2025-11-25",
            "policy": {"allowed_tools": [], "denied_tools": []},
            "sandbox": {
                "backend": "first-party-browser",
                "image": image,
                "browser_origins": origins(allowed),
                "browser_display": display,
            },
        }
    )
