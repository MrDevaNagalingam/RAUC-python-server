from typing import Literal

from pydantic import BaseModel, Field


class TargetCreate(BaseModel):
    tenant: str = Field(default="DEFAULT", pattern=r"^[A-Za-z0-9_-]{1,64}$")
    controller_id: str = Field(pattern=r"^[A-Za-z0-9_.-]{1,128}$")
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=2048)


class TargetPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2048)
    enabled: bool | None = None
    polling_interval_seconds: int | None = Field(default=None, ge=1, le=86399)


class FirmwareMetadata(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    version: str = Field(min_length=1, max_length=128)
    compatible: str = Field(min_length=1, max_length=255)
    vendor: str = Field(default="", max_length=255)
    description: str = Field(default="", max_length=8192)


class ModuleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    version: str = Field(min_length=1, max_length=128)
    type: Literal["os"] = "os"
    vendor: str = Field(default="", max_length=255)
    description: str = Field(default="", max_length=8192)
    artifact_id: int = Field(gt=0)


class DistributionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    version: str = Field(min_length=1, max_length=128)
    description: str = Field(default="", max_length=8192)
    module_id: int = Field(gt=0)


class DistributionPatch(BaseModel):
    description: str = Field(max_length=8192)


class DeploymentCreate(BaseModel):
    request_key: str = Field(pattern=r"^[A-Za-z0-9_-]{16,64}$")
    target_id: int = Field(gt=0)
    distribution_id: int = Field(gt=0)
    mode: Literal["forced", "download_only"] = "forced"
    expected_compatible: str = Field(min_length=1, max_length=255)
    expected_version: str = Field(min_length=1, max_length=128)
    operator_confirmed: Literal[True]
    approval_note: str = Field(min_length=10, max_length=2048)


class RetryRequest(BaseModel):
    request_key: str = Field(pattern=r"^[A-Za-z0-9_-]{16,64}$")
    operator_confirmed: Literal[True]
    approval_note: str = Field(min_length=10, max_length=2048)


class UserPatch(BaseModel):
    is_active: bool
