"""OS-protected credentials. There is no plaintext fallback or adjacent AES key."""

import base64
import copy
import hashlib
import json
import os
import platform
import re
import secrets
import shutil
import subprocess
import sys
from pathlib import Path

from joongi_hub.errors import RpcError
from joongi_hub.storage import atomic_json

SERVICE = "joongi-hub"
POWERSHELL = Path("/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe")


def dpapi(data, decrypt=False):
    import ctypes
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]

    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    target = Blob()
    function = (
        ctypes.windll.crypt32.CryptUnprotectData
        if decrypt
        else ctypes.windll.crypt32.CryptProtectData
    )
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise RpcError(-32045, "Windows DPAPI를 사용할 수 없습니다.")
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        ctypes.windll.kernel32.LocalFree(target.data)


def run(command, data=None):
    try:
        result = subprocess.run(command, input=data, capture_output=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RpcError(
            -32045, "OS 보안 저장소를 사용할 수 없습니다. 잠금과 실행 환경을 확인하세요."
        ) from exc
    if result.returncode:
        raise RpcError(-32045, "OS 보안 저장소가 잠겼거나 접근을 거절했습니다.")
    if len(result.stdout) > 4 * 1024**2:
        raise RpcError(-32045, "OS 보안 저장소 응답이 너무 큽니다.")
    return result.stdout.strip()


def wsl_dpapi(data, decrypt=False):
    operation = "Unprotect" if decrypt else "Protect"
    script = (
        "$ErrorActionPreference='Stop';Add-Type -AssemblyName System.Security;"
        + "$b=[Convert]::FromBase64String([Console]::In.ReadToEnd());"
        + f"$r=[Security.Cryptography.ProtectedData]::{operation}($b,$null,"
        + "[Security.Cryptography.DataProtectionScope]::CurrentUser);"
        + "[Console]::Out.Write([Convert]::ToBase64String($r))"
    )
    encoded = base64.b64encode(script.encode("utf-16-le")).decode()
    value = run(
        [str(POWERSHELL), "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
        base64.b64encode(data),
    )
    try:
        return base64.b64decode(value, validate=True)
    except ValueError as exc:
        raise RpcError(-32045, "Windows 보안 저장소의 응답을 확인할 수 없습니다.") from exc


class SystemVault:
    def __init__(self):
        self.name = "unavailable"
        if os.name == "nt":
            self.name = "windows-dpapi"
        elif sys.platform == "darwin":
            self.name = "macos-keychain"
        elif "microsoft" in platform.release().lower() and POWERSHELL.is_file():
            self.name = "wsl-windows-dpapi"
        elif shutil.which("secret-tool") and shutil.which("gdbus"):
            self.name = "linux-secret-service"

    def crypt(self, data, decrypt=False):
        return dpapi(data, decrypt) if self.name == "windows-dpapi" else wsl_dpapi(data, decrypt)

    def unlocked(self):
        if self.name != "linux-secret-service":
            return
        prefix = [
            shutil.which("gdbus"),
            "call",
            "--session",
            "--dest",
            "org.freedesktop.secrets",
            "--object-path",
        ]
        alias = run(
            [
                *prefix,
                "/org/freedesktop/secrets",
                "--method",
                "org.freedesktop.Secret.Service.ReadAlias",
                "default",
            ]
        ).decode()
        match = re.search(r"objectpath '(/[^']+)'", alias)
        if not match:
            raise RpcError(-32045, "기본 Secret Service 컬렉션을 먼저 설정하세요.")
        locked = run(
            [
                *prefix,
                match[1],
                "--method",
                "org.freedesktop.DBus.Properties.Get",
                "org.freedesktop.Secret.Collection",
                "Locked",
            ]
        ).decode()
        if "false" not in locked:
            raise RpcError(-32045, "Linux 로그인 키링을 잠금 해제하고 다시 시도하세요.")

    def entry(self, action, key, data=None):
        if self.name == "macos-keychain":
            from joongi_hub.native_keychain import item

            return item(action, SERVICE, key, data)
        if self.name != "linux-secret-service":
            raise RpcError(
                -32045,
                "OS 보안 저장소가 없습니다. Linux에서는 Secret Service와 secret-tool을 설정하세요.",
            )
        self.unlocked()
        tool = shutil.which("secret-tool")
        args = {
            "read": ["lookup"],
            "write": ["store", "--label=Joongi Hub credentials"],
            "delete": ["clear"],
        }[action]
        return run([tool, *args, "application", SERVICE, "state", key], data)


class CredentialStore:
    def __init__(self, path, vault=None):
        self.path = Path(path)
        self.vault = vault or SystemVault()
        self.identity = hashlib.sha256(str(self.path.resolve()).encode()).hexdigest()
        self.cache_key, self.cache = None, None

    def load(self):
        raw = self.path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if digest == self.cache_key and "dpapi" in self.vault.name:
            return copy.deepcopy(self.cache)
        marker = json.loads(raw)
        kind = marker.get("protected") if isinstance(marker, dict) else None
        if kind in {"windows-dpapi", "wsl-windows-dpapi"}:
            if self.vault.name not in {"windows-dpapi", "wsl-windows-dpapi"}:
                raise RpcError(
                    -32045, "이 인증 저장소는 원래 Windows 사용자 환경에서 열어야 합니다."
                )
            value = self.vault.crypt(base64.b64decode(marker["data"], validate=True), decrypt=True)
        elif kind in {"macos-keychain", "linux-secret-service"}:
            if kind != self.vault.name or not re.fullmatch(
                self.identity + r"-[a-f0-9]{32}", marker.get("key", "")
            ):
                raise RpcError(-32045, "인증 저장소와 OS 키링의 식별자가 일치하지 않습니다.")
            value = self.vault.entry("read", marker["key"])
            if not value:
                raise RpcError(-32045, "OS 키링의 인증 항목을 찾을 수 없습니다.")
        else:
            raise RpcError(
                -32045, "기존 평문 인증은 joongi-hub credentials --migrate로 먼저 이전하세요."
            )
        records = json.loads(value)
        if not isinstance(records, dict):
            raise RpcError(-32045, "인증 저장소의 형식이 올바르지 않습니다.")
        self.cache_key, self.cache = digest, copy.deepcopy(records)
        return records

    def save(self, records):
        if not records:
            if self.path.exists():
                old = json.loads(self.path.read_bytes())
                if old.get("key"):
                    self.vault.entry("delete", old["key"])
                self.path.unlink()
            self.cache_key, self.cache = None, None
            return
        data = json.dumps(records, ensure_ascii=False).encode()
        if len(data) > 512 * 1024:
            raise RpcError(-32045, "인증 저장소 크기 제한을 넘었습니다.")
        kind = self.vault.name
        if kind in {"windows-dpapi", "wsl-windows-dpapi"}:
            marker = {"protected": kind, "data": base64.b64encode(self.vault.crypt(data)).decode()}
        else:
            key = self.identity + "-" + secrets.token_hex(16)
            self.vault.entry("write", key, data)
            marker = {"protected": kind, "key": key}
        old = json.loads(self.path.read_bytes()) if self.path.exists() else {}
        atomic_json(self.path, marker)
        self.cache_key = None
        if old.get("key") and old.get("protected") == kind:
            try:
                self.vault.entry("delete", old["key"])
            except RpcError:
                pass  # A failed cleanup never replaces a committed marker with plaintext.

    def migrate(self):
        if not self.path.exists():
            return {"migrated": False, "storage": self.vault.name}
        records = json.loads(self.path.read_bytes())
        if "protected" in records:
            self.load()
            return {"migrated": False, "storage": self.vault.name}
        self.save(records)
        return {"migrated": True, "storage": self.vault.name}
