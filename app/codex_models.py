from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from .config import Settings

MODEL_VALUE_RE = re.compile(r"^[A-Za-z0-9._:+-]{1,120}$")
EFFORT_VALUE_RE = re.compile(r"^[a-z][a-z-]{1,32}$")
COMMON_REASONING_EFFORTS = ("low", "medium", "high")


def _read_toml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return tomllib.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except tomllib.TOMLDecodeError:
        return {}


def _quoted(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _auth_payload(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except json.JSONDecodeError:
        return {}


def _upsert_top_level_key(text: str, key: str, value: str) -> str:
    line = f"{key} = {_quoted(value)}"
    pattern = re.compile(rf"(?m)^{re.escape(key)}\s*=.*$")
    if pattern.search(text):
        return pattern.sub(line, text, count=1)

    rows = text.splitlines()
    insert_at = next((index for index, row in enumerate(rows) if row.startswith("[")), len(rows))
    rows.insert(insert_at, line)
    return "\n".join(rows).rstrip() + "\n"


def _turn_context_signal(payload: dict[str, Any]) -> tuple[str, str]:
    if not isinstance(payload, dict):
        return "", ""
    model = str(payload.get("model") or "").strip()
    effort = str(payload.get("effort") or "").strip()

    collaboration = payload.get("collaboration_mode") or {}
    if isinstance(collaboration, dict):
        settings = collaboration.get("settings") or {}
        if isinstance(settings, dict):
            model = model or str(settings.get("model") or "").strip()
            effort = effort or str(settings.get("reasoning_effort") or "").strip()
    return model, effort


@dataclass
class CodexModelRepository:
    settings: Settings

    @property
    def config_path(self) -> Path:
        return self.settings.codex_home / "config.toml"

    @property
    def auth_path(self) -> Path:
        return self.settings.codex_home / "auth.json"

    def _current_config(self) -> dict[str, Any]:
        data = _read_toml(self.config_path)
        provider_id = str(data.get("model_provider") or "").strip()
        providers = data.get("model_providers") or {}
        provider = providers.get(provider_id) if isinstance(providers, dict) else {}
        if not isinstance(provider, dict):
            provider = {}
        return {
            "model": str(data.get("model") or "").strip(),
            "effort": str(data.get("model_reasoning_effort") or "").strip(),
            "provider": provider_id,
            "providerName": str(provider.get("name") or provider_id).strip(),
            "baseUrl": str(provider.get("base_url") or "").strip(),
            "wireApi": str(provider.get("wire_api") or "").strip(),
        }

    def _provider_model_candidates(self, base_url: str) -> list[str]:
        text = str(base_url or "").strip()
        if not text:
            return []
        normalized = text if text.endswith("/") else f"{text}/"
        if normalized.rstrip("/").endswith("/v1"):
            return [urljoin(normalized, "models"), urljoin(text if text.endswith("/") else f"{text}/", "models")]
        return [urljoin(normalized, "v1/models"), urljoin(normalized, "models")]

    def _auth_headers(self) -> dict[str, str]:
        auth = _auth_payload(self.auth_path)
        api_key = str(auth.get("OPENAI_API_KEY") or "").strip()
        return {"Authorization": f"Bearer {api_key}"} if api_key else {}

    def _fetch_provider_models(self, current: dict[str, Any]) -> list[str]:
        base_url = current.get("baseUrl") or ""
        if not base_url:
            return [current["model"]] if current.get("model") else []

        headers = {"Accept": "application/json"}
        headers.update(self._auth_headers())
        errors: list[str] = []

        for url in self._provider_model_candidates(base_url):
            request = Request(url, headers=headers)
            try:
                with urlopen(request, timeout=8) as response:
                    payload = json.loads(response.read().decode("utf-8", errors="ignore"))
            except HTTPError as exc:
                errors.append(f"{url}: HTTP {exc.code}")
                continue
            except (URLError, TimeoutError, json.JSONDecodeError) as exc:
                errors.append(f"{url}: {exc}")
                continue

            rows = payload.get("data") if isinstance(payload, dict) else []
            if not isinstance(rows, list):
                continue

            models: list[str] = []
            for row in rows:
                if not isinstance(row, dict):
                    continue
                model_id = str(row.get("id") or row.get("model") or "").strip()
                model_type = str(row.get("type") or "model").strip().lower()
                if not model_id or model_type not in {"model", ""}:
                    continue
                models.append(model_id)

            if models:
                return sorted(set(models), key=lambda value: (value != current.get("model"), value.lower()))

        return [current["model"]] if current.get("model") else []

    def read_model_info(self) -> dict[str, Any]:
        current = self._current_config()
        efforts = {current["effort"]} if current["effort"] else set()
        efforts.update(COMMON_REASONING_EFFORTS)
        ordered_efforts = sorted(
            efforts,
            key=lambda value: (
                value != current["effort"],
                {"low": 1, "medium": 2, "high": 3}.get(value, 99),
                value,
            ),
        )

        return {
            "ok": True,
            "configPath": str(self.config_path),
            "current": current,
            "models": self._fetch_provider_models(current),
            "efforts": ordered_efforts,
        }

    def write_model_selection(self, model: str, effort: str) -> dict[str, Any]:
        model = (model or "").strip()
        effort = (effort or "").strip().lower()

        if not MODEL_VALUE_RE.fullmatch(model):
            raise ValueError("Invalid model value.")
        if not EFFORT_VALUE_RE.fullmatch(effort):
            raise ValueError("Invalid reasoning effort value.")

        original = self.config_path.read_text(encoding="utf-8", errors="ignore") if self.config_path.exists() else ""
        updated = _upsert_top_level_key(original, "model", model)
        updated = _upsert_top_level_key(updated, "model_reasoning_effort", effort)

        backup_dir = self.settings.codex_home / "backups" / f"codex-phone-model-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        backup_dir.mkdir(parents=True, exist_ok=True)
        (backup_dir / "config.toml").write_text(original, encoding="utf-8")

        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(updated, encoding="utf-8")

        result = self.read_model_info()
        result["updatedAt"] = datetime.utcnow().isoformat(timespec="seconds") + "Z"
        return result
