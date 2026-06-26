from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SendAttachment(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(default="image.png")
    type: str = Field(default="image/png")
    data_url: str = Field(alias="dataUrl")


class SendRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    text: str = ""
    thread_id: str = Field(default="", alias="threadId")
    attachments: list[SendAttachment] = Field(default_factory=list)


class SelectThreadRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    thread_id: str = Field(alias="threadId")


class NewThreadRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    project_path: str = Field(default="", alias="projectPath")


class InterruptRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    thread_id: str = Field(default="", alias="threadId")


class ModelSelectionRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    model: str
    effort: str


class AccessModeRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    mode: Literal["auto", "lan", "zerotier", "public", "remote"]


class PublicConfigRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    public_url: str = Field(default="", alias="publicUrl")
    enabled: bool = True
    provider: Literal["oray", "custom", "cloudflare", "ngrok", "frp"] = "oray"


class RemoteConfigRequest(PublicConfigRequest):
    remote_url: str = Field(default="", alias="remoteUrl")


class ZeroTierConfigRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    zerotier_ip: str = Field(default="", alias="zerotierIp")
    zerotier_port: int = Field(default=8787, alias="zerotierPort")
    enabled: bool = True


class TokenRotateRequest(BaseModel):
    force: bool = False


class StatusRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    thread_id: str = Field(default="", alias="threadId")
    session_file: str = Field(default="", alias="sessionFile")
    since: str = ""


class ThreadActionResult(BaseModel):
    ok: bool
    message: str
    thread_id: str = Field(default="", alias="threadId")
    sent_at: str = Field(default="", alias="sentAt")
    watch: dict = Field(default_factory=dict)


ThreadStatusLiteral = Literal["idle", "running", "complete", "error", "missing"]
