"""Local upstream credentials and browser/device OAuth, independent of Hub login."""

from __future__ import annotations

import base64
import hashlib
import ipaddress
import json
import math
import os
import re
import secrets
import time
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

from joongi_hub.credential_lock import CredentialLock
from joongi_hub.credential_store import CredentialStore, dpapi
from joongi_hub.errors import RpcError

AUTH_TYPES = {
    "none",
    "bearer",
    "api_key",
    "basic",
    "oauth",
    "device_code",
    "client_credentials",
    "external",
}
ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
AUTH_FIELDS = {
    "type",
    "token_env",
    "username_env",
    "password_env",
    "header",
    "prefix",
    "client_id",
    "client_secret_env",
    "client_auth_method",
    "issuer",
    "scopes",
    "resource_metadata_url",
    "authorization_endpoint",
    "token_endpoint",
    "registration_endpoint",
    "device_authorization_endpoint",
    "revocation_endpoint",
    "client_metadata_url",
}


def endpoint(value):
    if not isinstance(value, str) or len(value) > 4096:
        raise RpcError(-32602, "인증 URL이 올바르지 않습니다.")
    p = urlsplit(value)
    local = p.hostname in {"localhost", "127.0.0.1", "::1"}
    if p.hostname:
        try:
            local = ipaddress.ip_address(p.hostname).is_loopback
        except ValueError:
            pass
    if (
        not p.hostname
        or p.username
        or p.password
        or p.fragment
        or (p.scheme != "https" and not (p.scheme == "http" and local))
        or any(c in value for c in "\r\n")
    ):
        raise RpcError(-32602, "인증에는 HTTPS 또는 loopback HTTP 주소만 사용할 수 있습니다.")
    return value


def validate_auth(auth, transport):
    if not isinstance(auth, dict) or set(auth) - AUTH_FIELDS or auth.get("type") not in AUTH_TYPES:
        raise RpcError(-32602, "인증 설정의 필드나 방식이 올바르지 않습니다.")
    kind = auth["type"]
    if kind == "client_credentials" and not (
        auth.get("client_id") and auth.get("client_secret_env")
    ):
        raise RpcError(-32602, "Client Credentials에는 client ID와 secret 환경변수가 필요합니다.")
    if transport == "stdio" and kind not in {"none", "external"}:
        raise RpcError(-32602, "stdio 인증은 서버의 환경변수 또는 자체 로그인을 사용하세요.")
    for key, value in auth.items():
        if key == "scopes":
            if (
                not isinstance(value, list)
                or len(value) > 100
                or not all(
                    isinstance(s, str) and 0 < len(s) <= 200 and not re.search(r"[\s\x00-\x20]", s)
                    for s in value
                )
            ):
                raise RpcError(-32602, "scopes는 권한 이름의 배열이어야 합니다.")
        elif not isinstance(value, str) or len(value) > 4096 or "\n" in value or "\r" in value:
            raise RpcError(-32602, "인증 설정 값이 올바르지 않습니다.")
        elif key.endswith("_env") and not ENV_NAME.fullmatch(value):
            raise RpcError(-32602, "비밀 설정에는 값 대신 환경변수 이름을 지정하세요.")
        elif key.endswith("_endpoint") or key in {
            "issuer",
            "resource_metadata_url",
            "client_metadata_url",
        }:
            endpoint(value)
    if auth.get("client_auth_method", "none") not in {
        "none",
        "client_secret_basic",
        "client_secret_post",
    }:
        raise RpcError(-32602, "지원하지 않는 OAuth client 인증 방식입니다.")
    if not re.fullmatch(r"[A-Za-z0-9!#$%&'*+.^_`|~-]+", auth.get("header", "X-API-Key")):
        raise RpcError(-32602, "인증 헤더 이름이 올바르지 않습니다.")


def fingerprint(config):
    return hashlib.sha256(
        json.dumps(
            {"url": config.get("url"), "auth": config.get("auth", {})}, sort_keys=True
        ).encode()
    ).hexdigest()


def document(url, method="GET", data=None, headers=None):
    """Reuse DNS pinning, redirect rejection, size and wall-clock limits."""
    from joongi_hub.upstream import HttpTransport

    endpoint(url)
    response = HttpTransport({"url": url}).exchange(
        {"id": "auth"},
        raw={
            "method": method,
            "headers": headers or {"Accept": "application/json"},
            "body": data,
        },
    )
    try:
        value = json.loads(response["body"]) if response["body"].strip() else {}
    except (ValueError, UnicodeError) as exc:
        raise RpcError(-32040, "인증 서버가 올바른 JSON을 반환하지 않았습니다.") from exc
    if not isinstance(value, dict):
        raise RpcError(-32040, "인증 응답은 객체여야 합니다.")
    if response["status"] >= 400:
        # Never return provider descriptions, token responses or headers to tools/UI.
        error = value.get("error")
        code = (
            error
            if error
            in {
                "authorization_pending",
                "slow_down",
                "access_denied",
                "expired_token",
                "invalid_grant",
                "invalid_client",
            }
            else "oauth_error"
        )
        raise RpcError(-32040, "인증 서버가 요청을 거절했습니다.", {"reason": code})
    return value


class AuthManager:
    def __init__(self, state_dir: Path, store=None):
        self.path = Path(state_dir) / "auth" / "credentials.json"
        self.lock = CredentialLock(self.path.parent / "credentials.lock")
        self.pending = {}
        self.challenges = {}
        self.callback_url = None
        self.store = store or CredentialStore(self.path)

    def _read(self):
        if self.path.is_symlink() or self.path.parent.is_symlink():
            raise RpcError(-32040, "인증 저장소의 symlink는 지원하지 않습니다.")
        if not self.path.exists():
            return {}
        if self.path.stat().st_size > 1024 * 1024:
            raise RpcError(-32040, "인증 저장소 크기 제한을 넘었습니다.")
        try:
            return self.store.load()
        except (ValueError, UnicodeError, TypeError, KeyError) as exc:
            raise RpcError(-32040, "인증 저장소를 읽을 수 없습니다.") from exc

    @staticmethod
    def _crypt(data, decrypt=False):
        return dpapi(data, decrypt)

    def _write(self, records):
        self.store.save(records)

    def secret_values(self, config):
        with self.lock:
            row = self._record(config)
            token = row.get("token", {})
            values = [
                token.get("access_token"),
                token.get("refresh_token"),
                row.get("registration", {}).get("client_secret"),
            ]
            values += [v for k, v in row.get("manual", {}).items() if k != "username"]
            values += [
                os.environ.get(config.get("auth", {}).get(k, ""))
                for k in ("token_env", "password_env", "client_secret_env")
            ]
            values += [os.environ.get(v) for v in config.get("env", {}).values()]
            values += [os.environ.get(v) for v in config.get("headers", {}).values()]
            return [v for v in values if isinstance(v, str) and v]

    def _record(self, config):
        row = self._read().get(config["id"], {})
        return row if row.get("fingerprint") == fingerprint(config) else {}

    def _save(self, config, row):
        records = self._read()
        records[config["id"]] = {**row, "fingerprint": fingerprint(config)}
        self._write(records)

    def status(self, config):
        with self.lock:
            storage_error = None
            try:
                row = self._record(config)
            except RpcError as error:
                if error.code != -32045:
                    raise
                row, storage_error = {}, str(error)
            auth = config.get("auth", {})
            kind = auth.get(
                "type", "external" if config.get("env") or config.get("headers") else "none"
            )
            configured = bool(
                row.get("token")
                or row.get("manual")
                or os.environ.get(auth.get("token_env", ""))
                or (
                    os.environ.get(auth.get("username_env", ""))
                    and os.environ.get(auth.get("password_env", ""))
                )
            )
            token = row.get("token", {})
            expired = token.get("expires_at") is not None and token["expires_at"] <= time.time()
            rejected = self.challenges.get(config["id"], {}).get("fingerprint") == fingerprint(
                config
            )
            return {
                "type": kind,
                "configured": configured,
                "storage": self.store.vault.name,
                "storage_error": storage_error,
                "expires_at": token.get("expires_at"),
                "login_required": kind not in {"none", "external", "client_credentials"}
                and (not configured or rejected or (expired and not token.get("refresh_token"))),
                "pending": any(
                    p["server"] == config["id"] and p["expires"] > time.time()
                    for p in self.pending.values()
                ),
            }

    def set_manual(self, config, values):
        kind = config.get("auth", {}).get("type")
        keys = {"basic": {"username", "password"}, "bearer": {"token"}, "api_key": {"token"}}.get(
            kind
        )
        if (
            not keys
            or not isinstance(values, dict)
            or set(values) != keys
            or not all(
                isinstance(v, str) and 0 < len(v) <= 8192 and "\r" not in v and "\n" not in v
                for v in values.values()
            )
        ):
            raise RpcError(-32602, "선택한 인증 방식에 필요한 값을 입력하세요.")
        with self.lock:
            self._save(config, {"manual": values})
            self.challenges.pop(config["id"], None)
        return self.status(config)

    def challenge(self, config, value):
        if not isinstance(value, str) or len(value) > 8192:
            return
        fields = dict(re.findall(r'([A-Za-z_]+)="([^"\r\n]*)"', value))
        with self.lock:
            self.challenges[config["id"]] = {
                "fingerprint": fingerprint(config),
                **{k: fields[k] for k in ("resource_metadata", "scope") if k in fields},
            }

    def _metadata(self, config):
        auth = config.get("auth", {})
        resource = endpoint(config["url"])
        p = urlsplit(resource)
        origin = urlunsplit((p.scheme, p.netloc, "", "", ""))
        challenge = self.challenges.get(config["id"], {})
        if challenge.get("fingerprint") != fingerprint(config):
            challenge = {}
        if not challenge and not auth.get("resource_metadata_url") and not auth.get("issuer"):
            from joongi_hub.upstream import HttpTransport

            response = HttpTransport({"url": resource}).exchange(
                {"id": "auth-probe"},
                raw={"method": "GET", "headers": {"Accept": "application/json"}},
            )
            if response["status"] in {401, 403}:
                self.challenge(config, response["headers"].get("WWW-Authenticate", ""))
                challenge = self.challenges.get(config["id"], {})
        metadata_url = auth.get("resource_metadata_url") or challenge.get("resource_metadata")
        candidates = (
            [metadata_url]
            if metadata_url
            else [
                origin + "/.well-known/oauth-protected-resource" + p.path,
                origin + "/.well-known/oauth-protected-resource",
            ]
        )
        protected = None
        for url in dict.fromkeys(candidates):
            try:
                protected = document(url)
                break
            except RpcError:
                if metadata_url:
                    raise
        issuer = auth.get("issuer")
        if protected:
            if protected.get("resource") != resource:
                raise RpcError(-32040, "인증 metadata의 resource가 MCP 주소와 일치하지 않습니다.")
            issuers = protected.get("authorization_servers", [])
            if (
                not isinstance(issuers, list)
                or not issuers
                or not all(isinstance(i, str) for i in issuers)
            ):
                raise RpcError(-32040, "인증 서버의 issuer를 확인할 수 없습니다.")
            if issuer and issuer not in issuers:
                raise RpcError(-32040, "설정한 issuer가 MCP 인증 서버 목록과 다릅니다.")
            issuer = issuer or issuers[0]
        if not issuer:
            raise RpcError(-32040, "인증 서버를 발견하지 못했습니다. issuer를 지정하세요.")
        endpoint(issuer)
        parsed = urlsplit(issuer)
        root = urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))
        suffix = parsed.path.rstrip("/")
        locations = [
            root + "/.well-known/oauth-authorization-server" + suffix,
            root + "/.well-known/openid-configuration" + suffix,
            issuer.rstrip("/") + "/.well-known/openid-configuration",
        ]
        metadata = None
        for location in dict.fromkeys(locations):
            try:
                metadata = document(location)
            except RpcError:
                continue
            if metadata.get("issuer") != issuer:
                raise RpcError(-32040, "발견한 인증 metadata의 issuer가 일치하지 않습니다.")
            break
        if metadata is None:
            # Explicit endpoints support providers without discovery; issuer remains bound.
            if not auth.get("token_endpoint"):
                raise RpcError(-32040, "OAuth/OIDC metadata를 발견하지 못했습니다.")
            metadata = {"issuer": issuer}
        metadata = {**metadata, **{k: v for k, v in auth.items() if k.endswith("_endpoint")}}
        for key in (
            "authorization_endpoint",
            "token_endpoint",
            "registration_endpoint",
            "device_authorization_endpoint",
            "revocation_endpoint",
        ):
            if key in metadata:
                endpoint(metadata[key])
        scopes = list(dict.fromkeys([*auth.get("scopes", []), *challenge.get("scope", "").split()]))
        return metadata, resource, scopes

    def _registration(self, config, metadata, redirect):
        auth = config.get("auth", {})
        row = self._record(config)
        registration = row.get("registration", {})
        if auth.get("client_id"):
            if row.get("issuer") not in {None, metadata["issuer"]}:
                raise RpcError(-32040, "issuer가 변경되어 기존 client ID를 재사용할 수 없습니다.")
            return {
                "client_id": auth["client_id"],
                "token_endpoint_auth_method": auth.get(
                    "client_auth_method",
                    "client_secret_basic" if auth.get("client_secret_env") else "none",
                ),
            }
        if metadata.get("client_id_metadata_document_supported") and auth.get(
            "client_metadata_url"
        ):
            url = auth["client_metadata_url"]
            if not url.startswith("https://"):
                raise RpcError(-32602, "client metadata 문서는 HTTPS로 제공해야 합니다.")
            client = document(url)
            if (
                client.get("client_id") != url
                or redirect not in client.get("redirect_uris", [])
                or not client.get("client_name")
            ):
                raise RpcError(-32040, "client metadata 문서의 ID·redirect·이름을 확인하세요.")
            return {"client_id": url, "token_endpoint_auth_method": "none"}
        if (
            row.get("issuer") == metadata["issuer"]
            and registration.get("client_id")
            and registration.get("redirect_uri") == redirect
        ):
            return registration
        if not metadata.get("registration_endpoint"):
            raise RpcError(
                -32040, "이 서비스에 등록한 client_id 또는 client metadata URL을 지정하세요."
            )
        payload = {
            "client_name": "Joongi Hub",
            "redirect_uris": [redirect],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
            "application_type": "native",
        }
        if auth.get("type") == "device_code":
            payload["grant_types"] = [
                "urn:ietf:params:oauth:grant-type:device_code",
                "refresh_token",
            ]
            payload.pop("response_types", None)
            payload.pop("redirect_uris", None)
        registration = document(
            metadata["registration_endpoint"],
            "POST",
            json.dumps(payload).encode(),
            {"Content-Type": "application/json", "Accept": "application/json"},
        )
        if not isinstance(registration.get("client_id"), str) or not registration["client_id"]:
            raise RpcError(-32040, "client 등록 응답에 ID가 없습니다.")
        registration["redirect_uri"] = redirect
        registration["token_endpoint_auth_method"] = registration.get(
            "token_endpoint_auth_method", "none"
        )
        return registration

    def _token_request(self, config, metadata, registration, fields):
        auth = config.get("auth", {})
        fields = {**fields, "client_id": registration["client_id"]}
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        }
        secret = os.environ.get(auth.get("client_secret_env", "")) or registration.get(
            "client_secret"
        )
        method = registration.get("token_endpoint_auth_method", "none")
        if method in {"client_secret_basic", "client_secret_post"}:
            if not secret:
                raise RpcError(-32040, "OAuth client secret 환경변수를 확인하세요.")
            if method == "client_secret_basic":
                from urllib.parse import quote_plus

                raw = quote_plus(registration["client_id"]) + ":" + quote_plus(secret)
                headers["Authorization"] = "Basic " + base64.b64encode(raw.encode()).decode()
            else:
                fields["client_secret"] = secret
        elif method != "none":
            raise RpcError(-32040, "이 서비스의 client 인증 방식은 아직 지원하지 않습니다.")
        return document(metadata["token_endpoint"], "POST", urlencode(fields).encode(), headers)

    def _save_token(self, config, row, token):
        if (
            not isinstance(token.get("access_token"), str)
            or not token["access_token"]
            or len(token["access_token"]) > 65536
            or any(ord(c) < 33 or ord(c) > 126 for c in token["access_token"])
            or str(token.get("token_type", "Bearer")).lower() != "bearer"
        ):
            raise RpcError(-32040, "인증 응답에 지원하는 Bearer 토큰이 없습니다.")
        expires = token.get("expires_in")
        refresh = token.get("refresh_token")
        if "refresh_token" in token and (
            not isinstance(refresh, str)
            or not refresh
            or len(refresh) > 65536
            or any(ord(c) < 33 or ord(c) > 126 for c in refresh)
        ):
            raise RpcError(-32040, "인증 응답의 refresh token이 올바르지 않습니다.")
        try:
            seconds = float(expires) if expires is not None else None
            if seconds is not None and (not math.isfinite(seconds) or seconds < 0):
                raise ValueError
            expires_at = time.time() + seconds if seconds is not None else None
        except (ValueError, TypeError, OverflowError) as exc:
            raise RpcError(-32040, "토큰 만료 시간이 올바르지 않습니다.") from exc
        saved = {
            "access_token": token["access_token"],
            "refresh_token": token.get("refresh_token")
            or row.get("token", {}).get("refresh_token"),
            "expires_at": expires_at,
        }
        self._save(config, {**row, "token": saved})
        self.challenges.pop(config["id"], None)
        return saved

    def begin(self, config, redirect=None):
        if config.get("auth", {}).get("type") == "client_credentials":
            self.headers(config)
            return {"status": "authenticated"}
        if config.get("auth", {}).get("type") not in {"oauth", "device_code"}:
            raise RpcError(-32602, "브라우저 또는 device 인증 방식의 서버를 선택하세요.")
        redirect = (
            redirect
            or self.callback_url
            or ("http://127.0.0.1/" if config["auth"]["type"] == "device_code" else None)
        )
        if not redirect or (
            not redirect.startswith("http://127.0.0.1:") and config["auth"]["type"] != "device_code"
        ):
            raise RpcError(-32040, "로컬 Hub 관리 화면을 실행한 뒤 로그인하세요.")
        with self.lock:
            self.pending = {k: v for k, v in self.pending.items() if v["expires"] > time.time()}
            if len(self.pending) >= 32:
                raise RpcError(-32040, "진행 중인 인증이 너무 많습니다.")
            metadata, resource, scopes = self._metadata(config)
            registration = self._registration(config, metadata, redirect)
            row = {
                "issuer": metadata["issuer"],
                "metadata": metadata,
                "registration": registration,
                "resource": resource,
                "scopes": scopes,
            }
            self._save(config, {**self._record(config), **row})
            identity = secrets.token_urlsafe(32)
            pending = {
                "server": config["id"],
                "config": config,
                "fingerprint": fingerprint(config),
                "expires": time.time() + 600,
                "row": row,
                "redirect": redirect,
            }
            if config["auth"]["type"] == "device_code":
                url = metadata.get("device_authorization_endpoint")
                if not url:
                    raise RpcError(
                        -32040, "이 서비스는 device authorization endpoint를 제공하지 않습니다."
                    )
                fields = {"client_id": registration["client_id"], "resource": resource}
                if scopes:
                    fields["scope"] = " ".join(scopes)
                device = document(
                    url,
                    "POST",
                    urlencode(fields).encode(),
                    {
                        "Content-Type": "application/x-www-form-urlencoded",
                        "Accept": "application/json",
                    },
                )
                verification = endpoint(device.get("verification_uri", ""))
                pending.update(
                    device_code=device.get("device_code"),
                    interval=max(5, int(device.get("interval", 5))),
                    next_poll=0,
                )
                pending["expires"] = time.time() + min(
                    1800, max(1, int(device.get("expires_in", 600)))
                )
                if not isinstance(pending["device_code"], str) or not isinstance(
                    device.get("user_code"), str
                ):
                    raise RpcError(-32040, "device 인증 응답을 확인할 수 없습니다.")
                self.pending[identity] = pending
                return {
                    "flow": "device_code",
                    "login_id": identity,
                    "url": verification,
                    "user_code": device["user_code"],
                    "interval": pending["interval"],
                }
            if not metadata.get("authorization_endpoint"):
                raise RpcError(-32040, "authorization endpoint가 없습니다.")
            supported = metadata.get("code_challenge_methods_supported")
            if not isinstance(supported, list) or "S256" not in supported:
                raise RpcError(-32040, "이 서비스는 PKCE S256을 지원하지 않습니다.")
            verifier = secrets.token_urlsafe(64)
            pending["verifier"] = verifier
            self.pending[identity] = pending
            fields = {
                "response_type": "code",
                "client_id": registration["client_id"],
                "redirect_uri": redirect,
                "state": identity,
                "code_challenge": base64.urlsafe_b64encode(
                    hashlib.sha256(verifier.encode()).digest()
                )
                .decode()
                .rstrip("="),
                "code_challenge_method": "S256",
                "resource": resource,
            }
            if scopes:
                fields["scope"] = " ".join(scopes)
            url = metadata["authorization_endpoint"]
            return {
                "flow": "authorization_code",
                "login_id": identity,
                "url": url + ("&" if "?" in url else "?") + urlencode(fields),
            }

    def complete(self, query):
        values = parse_qs(query)
        if any(len(v) != 1 for v in values.values()):
            raise RpcError(-32602, "중복된 OAuth 응답 값입니다.")
        state = values.get("state", [""])[0]
        with self.lock:
            pending = self.pending.pop(state, None)
            if not pending or pending["expires"] <= time.time() or "verifier" not in pending:
                raise RpcError(-32040, "로그인 요청이 만료됐거나 state가 올바르지 않습니다.")
            if "error" in values or not values.get("code"):
                raise RpcError(-32040, "로그인이 취소되었거나 인증 코드가 없습니다.")
            row = pending["row"]
            if (
                row["metadata"].get("authorization_response_iss_parameter_supported")
                and "iss" not in values
            ):
                raise RpcError(-32040, "OAuth 응답에 issuer가 없습니다.")
            if values.get("iss", [row["issuer"]])[0] != row["issuer"]:
                raise RpcError(-32040, "OAuth 응답의 issuer가 일치하지 않습니다.")
            token = self._token_request(
                pending["config"],
                row["metadata"],
                row["registration"],
                {
                    "grant_type": "authorization_code",
                    "code": values["code"][0],
                    "redirect_uri": pending["redirect"],
                    "code_verifier": pending["verifier"],
                    "resource": row["resource"],
                },
            )
            self._save_token(pending["config"], row, token)
            return {"authenticated": True, "server": pending["server"]}

    def poll(self, config, identity):
        with self.lock:
            pending = self.pending.get(identity)
            if (
                not pending
                or pending["server"] != config["id"]
                or pending["fingerprint"] != fingerprint(config)
                or pending["expires"] <= time.time()
                or "device_code" not in pending
            ):
                raise RpcError(-32040, "device 로그인 요청이 만료됐거나 대상이 다릅니다.")
            now = time.time()
            if now < pending["next_poll"]:
                return {"status": "pending", "interval": pending["interval"]}
            pending["next_poll"] = now + pending["interval"]
            row = pending["row"]
            try:
                token = self._token_request(
                    config,
                    row["metadata"],
                    row["registration"],
                    {
                        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                        "device_code": pending["device_code"],
                        "resource": row["resource"],
                    },
                )
            except RpcError as exc:
                reason = (exc.data or {}).get("reason")
                if reason in {"authorization_pending", "slow_down"}:
                    if reason == "slow_down":
                        pending["interval"] += 5
                    return {"status": "pending", "interval": pending["interval"]}
                self.pending.pop(identity, None)
                raise
            self._save_token(config, row, token)
            self.pending.pop(identity, None)
            return {"status": "authenticated"}

    def headers(self, config, allow_anonymous=False):
        auth = config.get("auth", {})
        kind = auth.get("type", "none")
        if kind in {"none", "external"}:
            return {}
        with self.lock:
            row = self._record(config)
            manual = row.get("manual", {})
            if kind in {"bearer", "api_key"}:
                value = os.environ.get(auth.get("token_env", "")) or manual.get("token")
                if not value:
                    raise RpcError(-32040, "인증 토큰 환경변수 또는 로컬 자격증명을 설정하세요.")
                return (
                    {"Authorization": "Bearer " + value}
                    if kind == "bearer"
                    else {auth.get("header", "X-API-Key"): auth.get("prefix", "") + value}
                )
            if kind == "basic":
                username = os.environ.get(auth.get("username_env", "")) or manual.get("username")
                password = os.environ.get(auth.get("password_env", "")) or manual.get("password")
                if not username or not password:
                    raise RpcError(-32040, "Basic 인증의 계정 환경변수 또는 자격증명을 설정하세요.")
                return {
                    "Authorization": "Basic "
                    + base64.b64encode((username + ":" + password).encode()).decode()
                }
            token = row.get("token", {})
            expired = (
                token.get("expires_at") is not None and token["expires_at"] <= time.time() + 30
            )
            if kind == "client_credentials" and (not token or expired):
                metadata, resource, scopes = self._metadata(config)
                registration = self._registration(
                    config, metadata, self.callback_url or "http://127.0.0.1/"
                )
                fields = {"grant_type": "client_credentials", "resource": resource}
                if scopes:
                    fields["scope"] = " ".join(scopes)
                row = {
                    "issuer": metadata["issuer"],
                    "metadata": metadata,
                    "registration": registration,
                    "resource": resource,
                    "scopes": scopes,
                }
                token = self._save_token(
                    config, row, self._token_request(config, metadata, registration, fields)
                )
            elif expired and token.get("refresh_token"):
                try:
                    updated = self._token_request(
                        config,
                        row["metadata"],
                        row["registration"],
                        {
                            "grant_type": "refresh_token",
                            "refresh_token": token["refresh_token"],
                            "resource": row["resource"],
                        },
                    )
                    token = self._save_token(config, row, updated)
                except RpcError:
                    self.logout(config, revoke=False)
                    raise RpcError(-32040, "인증 갱신에 실패했습니다. 다시 로그인하세요.") from None
            if not token and allow_anonymous and kind in {"oauth", "device_code"}:
                return {}
            if not token or (
                expired and not token.get("refresh_token") and kind != "client_credentials"
            ):
                raise RpcError(-32040, "로그인이 필요하거나 토큰이 만료되었습니다.")
            return {"Authorization": "Bearer " + token["access_token"]}

    def refresh_rejected(self, config, rejected):
        with self.lock:
            row = self._record(config)
            token = row.get("token", {})
            if not token.get("refresh_token"):
                return False
            if rejected != "Bearer " + token.get("access_token", ""):
                return True
            try:
                updated = self._token_request(
                    config,
                    row["metadata"],
                    row["registration"],
                    {
                        "grant_type": "refresh_token",
                        "refresh_token": token["refresh_token"],
                        "resource": row["resource"],
                    },
                )
                self._save_token(config, row, updated)
                return True
            except RpcError:
                self.logout(config, revoke=False)
                return False

    def logout(self, config, revoke=True):
        with self.lock:
            row = self._record(config)
            revoked = False
            token = row.get("token", {})
            metadata = row.get("metadata", {})
            if revoke and token and metadata.get("revocation_endpoint"):
                try:
                    self._token_request(
                        config,
                        {**metadata, "token_endpoint": metadata["revocation_endpoint"]},
                        row["registration"],
                        {
                            "token": token.get("refresh_token") or token["access_token"],
                            "token_type_hint": "refresh_token"
                            if token.get("refresh_token")
                            else "access_token",
                        },
                    )
                    revoked = True
                except RpcError:
                    pass
            records = self._read()
            records.pop(config["id"], None)
            self._write(records)
            self.pending = {k: v for k, v in self.pending.items() if v["server"] != config["id"]}
            self.challenges.pop(config["id"], None)
        return {"logged_out": True, "revoked": revoked}
