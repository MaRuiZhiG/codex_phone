from __future__ import annotations

import json
import ipaddress
import socket
import subprocess
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from .config import Settings

AccessMode = Literal["auto", "lan", "zerotier", "public"]
PublicProvider = Literal["oray", "custom", "cloudflare", "ngrok", "frp"]
ALLOWED_MODES: set[str] = {"auto", "lan", "zerotier", "public", "remote"}
ALLOWED_PROVIDERS: set[str] = {"oray", "custom", "cloudflare", "ngrok", "frp"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _best_lan_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            host = sock.getsockname()[0]
            if host and not host.startswith("127."):
                return host
    except OSError:
        pass

    try:
        host = socket.gethostbyname(socket.gethostname())
        if host and not host.startswith("127."):
            return host
    except OSError:
        pass

    return "127.0.0.1"


def _normalize_remote_url(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if "://" not in text:
        text = f"https://{text}"
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Remote URL is invalid.")
    return parsed.geturl().rstrip("/")


def _normalize_ip(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        return str(ipaddress.ip_address(text))
    except ValueError as exc:
        raise ValueError("ZeroTier IP is invalid.") from exc


def _dedupe_keep_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def _local_ipv4_addresses() -> set[str]:
    addresses = {"127.0.0.1"}

    try:
        result = subprocess.run(
            ["ipconfig"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=5,
        )
        for match in re.finditer(r"(?<!\d)(\d{1,3}(?:\.\d{1,3}){3})(?!\d)", result.stdout or ""):
            raw_ip = match.group(1)
            try:
                addresses.add(str(ipaddress.ip_address(raw_ip)))
            except ValueError:
                continue
    except (OSError, subprocess.SubprocessError):
        pass

    try:
        for item in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            addresses.add(item[4][0])
    except OSError:
        pass

    return addresses


@dataclass
class AccessManager:
    settings: Settings

    @property
    def state_path(self) -> Path:
        return self.settings.state_dir / "access.json"

    def _default_state(self) -> dict[str, Any]:
        return {
            "mode": "auto",
            "zerotier_ip": "",
            "zerotier_port": self.settings.port,
            "zerotier_enabled": False,
            "zerotier_status": "not_configured",
            "public_url": "",
            "public_enabled": False,
            "public_provider": "oray",
            "public_status": "not_configured",
            "updated_at": _now_iso(),
        }

    def _read_state(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return self._default_state()
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8", errors="ignore"))
        except json.JSONDecodeError:
            return self._default_state()
        if not isinstance(payload, dict):
            return self._default_state()
        state = self._default_state()
        state.update(payload)
        return state

    def _write_state(self, state: dict[str, Any]) -> dict[str, Any]:
        state["updated_at"] = _now_iso()
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return state

    def _computed_lan_url(self) -> str:
        return f"http://{_best_lan_ip()}:{self.settings.port}"

    def _zerotier_url(self, state: dict[str, Any]) -> str:
        ip = str(state.get("zerotier_ip") or "").strip()
        port = int(state.get("zerotier_port") or self.settings.port)
        if not ip:
            return ""
        return f"http://{ip}:{port}"

    def detect_zerotier_ips(self) -> list[str]:
        try:
            result = subprocess.run(
                ["ipconfig"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="ignore",
                timeout=5,
            )
        except (OSError, subprocess.SubprocessError):
            return []

        candidates: list[str] = []
        blocks = re.split(r"\r?\n\r?\n+", result.stdout or "")
        for block in blocks:
            if "ZeroTier" not in block:
                continue
            for match in re.finditer(r"(?<!\d)(\d{1,3}(?:\.\d{1,3}){3})(?!\d)", block):
                raw_ip = match.group(1)
                try:
                    parsed = ipaddress.ip_address(raw_ip)
                except ValueError:
                    continue
                if parsed.version != 4 or not parsed.is_private:
                    continue
                if raw_ip.startswith(("127.", "169.254.")):
                    continue
                candidates.append(raw_ip)

        return _dedupe_keep_order(candidates)

    def read_status(self) -> dict[str, Any]:
        state = self._read_state()
        detected_zerotier_ips = self.detect_zerotier_ips()
        saved_zerotier_ip = str(state.get("zerotier_ip") or "").strip()
        if not saved_zerotier_ip and detected_zerotier_ips:
            saved_zerotier_ip = detected_zerotier_ips[0]
            state["zerotier_ip"] = saved_zerotier_ip
            state["zerotier_enabled"] = True
            self._write_state(state)
        zerotier_url = self._zerotier_url(state)
        zerotier_enabled = bool(state.get("zerotier_enabled")) and bool(zerotier_url)
        zerotier_status = "connected" if zerotier_enabled else ("configured" if zerotier_url else "not_configured")
        public_url = str(state.get("public_url") or "").strip()
        public_enabled = bool(state.get("public_enabled")) and bool(public_url)
        public_status = "connected" if public_enabled else ("configured" if public_url else "not_configured")
        preferred_mode = str(state.get("mode") or "auto").strip().lower()
        if preferred_mode == "remote":
            preferred_mode = "public"
        if preferred_mode not in {"auto", "lan", "zerotier", "public"}:
            preferred_mode = "auto"

        lan_url = self._computed_lan_url()
        effective_mode = preferred_mode
        effective_url = lan_url
        if preferred_mode == "zerotier" and zerotier_enabled:
            effective_url = zerotier_url
        elif preferred_mode == "zerotier":
            effective_mode = "lan"
        elif preferred_mode == "public" and public_enabled:
            effective_url = public_url
        elif preferred_mode == "public":
            effective_mode = "lan"
        elif preferred_mode == "auto" and zerotier_enabled:
            effective_mode = "zerotier"
            effective_url = zerotier_url
        elif preferred_mode == "auto" and public_enabled:
            effective_mode = "public"
            effective_url = public_url

        return {
            "ok": True,
            "mode": preferred_mode,
            "effectiveMode": effective_mode,
            "lanUrl": lan_url,
            "zerotierIp": str(state.get("zerotier_ip") or ""),
            "zerotierIps": detected_zerotier_ips,
            "zerotierPort": int(state.get("zerotier_port") or self.settings.port),
            "zerotierUrl": zerotier_url,
            "zerotierEnabled": zerotier_enabled,
            "zerotierStatus": zerotier_status,
            "publicUrl": public_url,
            "publicEnabled": public_enabled,
            "publicProvider": str(state.get("public_provider") or "oray"),
            "publicStatus": public_status,
            "remoteUrl": public_url,
            "remoteEnabled": public_enabled,
            "remoteProvider": str(state.get("public_provider") or "oray"),
            "remoteStatus": public_status,
            "effectiveUrl": effective_url,
            "statePath": str(self.state_path),
            "updatedAt": str(state.get("updated_at") or _now_iso()),
        }

    def set_mode(self, mode: str) -> dict[str, Any]:
        normalized = str(mode or "").strip().lower()
        if normalized == "remote":
            normalized = "public"
        if normalized not in ALLOWED_MODES:
            raise ValueError("Mode must be auto, lan, zerotier, or public.")
        state = self._read_state()
        state["mode"] = normalized
        self._write_state(state)
        return self.read_status()

    def configure_public(self, remote_url: str, enabled: bool, provider: str = "oray") -> dict[str, Any]:
        normalized_provider = str(provider or "oray").strip().lower()
        if normalized_provider not in ALLOWED_PROVIDERS:
            raise ValueError("Public provider is invalid.")

        normalized_url = _normalize_remote_url(remote_url) if remote_url else ""
        state = self._read_state()
        state["public_url"] = normalized_url
        state["public_enabled"] = bool(enabled and normalized_url)
        state["public_provider"] = normalized_provider
        state["public_status"] = "configured" if normalized_url else "not_configured"
        self._write_state(state)
        return self.read_status()

    def configure_remote(self, remote_url: str, enabled: bool, provider: str = "oray") -> dict[str, Any]:
        return self.configure_public(remote_url, enabled, provider)

    def configure_zerotier(self, ip: str, port: int, enabled: bool) -> dict[str, Any]:
        normalized_ip = _normalize_ip(ip) if ip else ""
        normalized_port = int(port or self.settings.port)
        if normalized_port < 1 or normalized_port > 65535:
            raise ValueError("ZeroTier port is invalid.")

        state = self._read_state()
        state["zerotier_ip"] = normalized_ip
        state["zerotier_port"] = normalized_port
        state["zerotier_enabled"] = bool(enabled and normalized_ip)
        state["zerotier_status"] = "configured" if normalized_ip else "not_configured"
        self._write_state(state)
        return self.read_status()

    def check_remote(self) -> dict[str, Any]:
        return self.check_public()

    def check_public(self) -> dict[str, Any]:
        status = self.read_status()
        status["checkedAt"] = _now_iso()
        return status

    def check_zerotier(self) -> dict[str, Any]:
        status = self.read_status()
        checked_at = _now_iso()
        zerotier_url = str(status.get("zerotierUrl") or "").strip()

        result = {
            "ok": bool(zerotier_url),
            "checkedAt": checked_at,
            "baseUrl": zerotier_url,
            "healthUrl": "",
            "reachable": False,
            "statusCode": 0,
            "error": "",
        }

        if not zerotier_url:
            status["checkedAt"] = checked_at
            status["zerotierCheck"] = result
            return status

        query = urlencode({"token": self.settings.token})
        health_url = f"{zerotier_url}/health?{query}"
        result["healthUrl"] = health_url
        parsed = urlparse(zerotier_url)
        host = parsed.hostname or ""
        port = int(parsed.port or self.settings.port)

        if host in _local_ipv4_addresses() and port == int(self.settings.port):
            try:
                with socket.create_connection((host, port), timeout=2):
                    result["statusCode"] = 200
                    result["reachable"] = True
                    result["ok"] = True
            except OSError as exc:
                result["error"] = str(exc)
            status["checkedAt"] = checked_at
            status["zerotierCheck"] = result
            return status

        try:
            req = Request(health_url, method="GET")
            with urlopen(req, timeout=4) as response:
                result["statusCode"] = int(getattr(response, "status", 200) or 200)
                result["reachable"] = 200 <= result["statusCode"] < 300
                result["ok"] = result["reachable"]
        except HTTPError as exc:
            result["statusCode"] = int(exc.code or 0)
            result["error"] = f"HTTP {exc.code}"
        except URLError as exc:
            result["error"] = str(exc.reason or exc)
        except OSError as exc:
            result["error"] = str(exc)

        status["checkedAt"] = checked_at
        status["zerotierCheck"] = result
        return status
