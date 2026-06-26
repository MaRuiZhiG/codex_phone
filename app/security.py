from __future__ import annotations

from fastapi import HTTPException, Request, status

from .config import Settings


def _parse_cookies(header: str) -> dict[str, str]:
    cookies: dict[str, str] = {}
    for chunk in (header or "").split(";"):
        if "=" not in chunk:
            continue
        key, value = chunk.split("=", 1)
        key = key.strip()
        if key:
            cookies[key] = value.strip()
    return cookies


def authorize(request: Request, settings: Settings) -> None:
    header_token = request.headers.get("x-mobile-typer-token", "").strip()
    query_token = request.query_params.get("token", "").strip()
    cookie_token = _parse_cookies(request.headers.get("cookie", "")).get("codexPhoneToken", "").strip()

    if settings.token in {header_token, query_token, cookie_token}:
        return

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"ok": False, "code": "UNAUTHORIZED", "message": "Bad or missing token."},
    )
