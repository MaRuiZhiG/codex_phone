from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import Settings

THREAD_ID_RE = re.compile(r"([a-f0-9]{8}-[a-f0-9-]{27,})\.jsonl$", re.IGNORECASE)
MAX_TAIL_BYTES = 5 * 1024 * 1024
MAX_HISTORY_BYTES = 24 * 1024 * 1024


def _parse_iso(value: str) -> datetime | None:
    text = (value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _tail_lines(path: Path, max_bytes: int) -> list[str]:
    size = path.stat().st_size
    start = max(0, size - max_bytes)
    with path.open("rb") as handle:
        handle.seek(start)
        data = handle.read()
    text = data.decode("utf-8", errors="ignore")
    if start > 0 and "\n" in text:
        text = text.split("\n", 1)[1]
    return [line for line in text.splitlines() if line.strip()]


def _jsonl_objects(path: Path, max_bytes: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in _tail_lines(path, max_bytes):
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _extract_message_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for item in content:
        if isinstance(item, str):
            parts.append(item)
        elif isinstance(item, dict):
            text = item.get("text") or item.get("message") or ""
            if text:
                parts.append(str(text))
    return "\n".join(parts).strip()


def _is_failure_payload(payload: dict[str, Any]) -> bool:
    keys = [payload.get("type"), payload.get("status"), payload.get("code"), payload.get("error"), payload.get("reason")]
    merged = " ".join(str(item or "").lower() for item in keys)
    return any(word in merged for word in ["error", "fail", "timeout", "abort", "cancel", "unavailable"])


@dataclass
class SessionRepository:
    settings: Settings

    def list_session_files(self) -> list[Path]:
        if not self.settings.codex_sessions_dir.exists():
            return []
        return sorted(self.settings.codex_sessions_dir.rglob("*.jsonl"), key=lambda item: item.stat().st_mtime, reverse=True)

    def thread_id_from_file(self, path: Path) -> str:
        match = THREAD_ID_RE.search(path.name)
        return match.group(1) if match else ""

    def is_thread_id(self, value: str) -> bool:
        return bool(re.fullmatch(r"[a-f0-9]{8}-[a-f0-9-]{27,}", (value or "").strip(), re.IGNORECASE))

    def read_thread_index(self) -> dict[str, dict[str, str]]:
        out: dict[str, dict[str, str]] = {}
        path = self.settings.codex_session_index
        if not path.exists():
            return out
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            thread_id = str(item.get("id") or "")
            if thread_id:
                out[thread_id] = {
                    "name": str(item.get("thread_name") or ""),
                    "updated_at": str(item.get("updated_at") or ""),
                }
        return out

    def read_session_meta(self, path: Path) -> dict[str, Any]:
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            for _, line in zip(range(60), handle):
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if item.get("type") == "session_meta":
                    payload = item.get("payload") or {}
                    return payload if isinstance(payload, dict) else {}
        return {}

    def find_file_by_thread_id(self, thread_id: str) -> Path | None:
        if not self.is_thread_id(thread_id):
            return None
        for path in self.list_session_files():
            if thread_id in path.name:
                return path
        return None

    def find_latest_file(self) -> Path | None:
        files = self.list_session_files()
        return files[0] if files else None

    def wait_for_latest_file(
        self,
        previous_thread_id: str = "",
        previous_mtime: float = 0.0,
        timeout_seconds: float = 8.0,
        interval_seconds: float = 0.35,
    ) -> Path | None:
        deadline = time.time() + timeout_seconds
        best: Path | None = None
        while time.time() < deadline:
            latest = self.find_latest_file()
            if latest:
                try:
                    stat = latest.stat()
                    thread_id = self.thread_id_from_file(latest)
                except OSError:
                    latest = None
                else:
                    if thread_id and thread_id != previous_thread_id and stat.st_mtime >= previous_mtime:
                        return latest
                    best = latest
            time.sleep(interval_seconds)
        return best

    def list_threads(self, limit: int = 80) -> list[dict[str, Any]]:
        index = self.read_thread_index()
        threads: list[dict[str, Any]] = []
        for path in self.list_session_files()[: max(limit * 3, limit)]:
            thread_id = self.thread_id_from_file(path)
            if not thread_id:
                continue
            meta = self.read_session_meta(path)
            stat = path.stat()
            info = index.get(thread_id, {})
            updated_at = info.get("updated_at") or meta.get("timestamp") or datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
            threads.append(
                {
                    "id": thread_id,
                    "name": info.get("name") or self.first_user_message(path) or "Untitled thread",
                    "updatedAt": updated_at,
                    "sessionFile": path.name,
                    "cwd": str(meta.get("cwd") or ""),
                    "source": str(meta.get("source") or ""),
                    "threadSource": str(meta.get("thread_source") or ""),
                    "mtimeMs": int(stat.st_mtime * 1000),
                }
            )
            if len(threads) >= limit:
                break
        return threads

    def first_user_message(self, path: Path) -> str:
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            for _, line in zip(range(300), handle):
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                payload = item.get("payload") or {}
                if item.get("type") == "event_msg" and payload.get("type") == "user_message":
                    return _normalize_text(payload.get("message") or "")[:80]
        return ""

    def parse_history(self, thread_id: str, limit: int = 80) -> dict[str, Any]:
        path = self.find_file_by_thread_id(thread_id)
        if not path:
            return {"ok": True, "available": False, "threadId": thread_id, "messages": []}

        messages: list[dict[str, Any]] = []
        for item in _jsonl_objects(path, MAX_HISTORY_BYTES):
            payload = item.get("payload") or {}
            item_type = item.get("type")

            if item_type == "event_msg" and payload.get("type") == "user_message":
                text = str(payload.get("message") or "").strip()
                images = payload.get("local_images") or payload.get("images") or []
                messages.append(
                    {
                        "role": "user",
                        "label": "You",
                        "text": text,
                        "attachments": images,
                        "timestamp": item.get("timestamp") or "",
                    }
                )
                continue

            if item_type == "response_item" and payload.get("type") == "message" and payload.get("role") == "assistant":
                if payload.get("phase") != "final_answer":
                    continue
                text = _extract_message_text(payload.get("content"))
                if text:
                    messages.append(
                        {
                            "role": "assistant",
                            "label": "Codex",
                            "text": text,
                            "timestamp": item.get("timestamp") or "",
                        }
                    )
                continue

            if item_type == "event_msg" and _is_failure_payload(payload):
                messages.append(
                    {
                        "role": "assistant",
                        "label": "Codex error",
                        "text": _normalize_text(payload.get("message") or payload.get("detail") or payload.get("reason") or "Codex ended with an error."),
                        "timestamp": item.get("timestamp") or "",
                    }
                )

        return {
            "ok": True,
            "available": True,
            "threadId": thread_id,
            "sessionFile": path.name,
            "messages": messages[-limit:],
        }

    def parse_status(self, thread_id: str = "", session_file: str = "", since: str = "") -> dict[str, Any]:
        path: Path | None = None
        if thread_id:
            path = self.find_file_by_thread_id(thread_id)
        elif session_file:
            candidate = self.settings.codex_sessions_dir.rglob(session_file)
            path = next(candidate, None)
        else:
            path = self.find_latest_file()

        if not path:
            return {
                "ok": True,
                "available": False,
                "status": "missing",
                "preview": "No Codex session file found.",
                "final": "",
                "threadId": thread_id,
                "sessionFile": "",
                "updatedAt": _iso_now(),
            }

        since_dt = _parse_iso(since)
        status = "idle"
        preview = "Waiting for Codex."
        final = ""
        started_at = ""
        completed_at = ""
        latest_ts = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()
        current_turn: str = ""
        steps: list[dict[str, str]] = []

        for item in _jsonl_objects(path, MAX_TAIL_BYTES):
            timestamp = str(item.get("timestamp") or "")
            item_dt = _parse_iso(timestamp)
            if since_dt and item_dt and item_dt < since_dt:
                continue

            payload = item.get("payload") or {}
            item_type = item.get("type")

            if item_type == "event_msg" and payload.get("type") == "task_started":
                status = "running"
                started_at = timestamp
                current_turn = str(payload.get("turn_id") or "")
                preview = "Codex started working."
                steps.append({"timestamp": timestamp, "label": "task_started", "text": preview})
                continue

            if item_type == "event_msg" and payload.get("type") == "agent_message":
                preview = str(payload.get("message") or preview)
                status = "running"
                steps.append({"timestamp": timestamp, "label": "agent_message", "text": preview})
                continue

            if item_type == "response_item" and payload.get("type") == "message" and payload.get("role") == "assistant":
                text = _extract_message_text(payload.get("content"))
                if text:
                    preview = text[:200]
                    status = "running" if payload.get("phase") != "final_answer" else "complete"
                    if payload.get("phase") == "final_answer":
                        final = text
                        completed_at = timestamp
                    steps.append({"timestamp": timestamp, "label": str(payload.get("phase") or "assistant"), "text": preview})
                continue

            if item_type == "event_msg" and payload.get("type") == "task_complete":
                status = "complete"
                completed_at = timestamp
                if not final:
                    final = str(payload.get("last_agent_message") or "").strip()
                preview = final[:200] if final else "Codex finished."
                steps.append({"timestamp": timestamp, "label": "task_complete", "text": preview})
                continue

            if item_type == "event_msg" and _is_failure_payload(payload):
                status = "error"
                completed_at = timestamp
                preview = _normalize_text(payload.get("message") or payload.get("detail") or payload.get("reason") or "Codex failed.")
                final = final or preview
                steps.append({"timestamp": timestamp, "label": "error", "text": preview})

        return {
            "ok": True,
            "available": True,
            "status": status,
            "preview": preview,
            "final": final,
            "threadId": self.thread_id_from_file(path),
            "sessionFile": path.name,
            "turnId": current_turn,
            "startedAt": started_at,
            "completedAt": completed_at,
            "updatedAt": latest_ts,
            "steps": steps[-12:],
        }
