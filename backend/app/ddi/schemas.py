from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

AttributeKey = Annotated[str, StringConstraints(min_length=1, max_length=128)]
AttributeValue = Annotated[str, StringConstraints(strict=True, max_length=2048)]


class ConfigData(BaseModel):
    # hawkBit ignores unknown fields; the v1.3 client includes time/status.
    model_config = ConfigDict(extra="ignore")
    mode: Literal["merge", "replace", "remove"] = "merge"
    data: dict[AttributeKey, AttributeValue] = Field(min_length=1, max_length=100)


class Polling(BaseModel):
    sleep: str = Field(pattern=r"^\d{2}:[0-5]\d:[0-5]\d$")


class ControllerConfig(BaseModel):
    polling: Polling


class Link(BaseModel):
    href: str


class ControllerResponse(BaseModel):
    config: ControllerConfig
    links: dict[str, Link] = Field(alias="_links")


class FeedbackResult(BaseModel):
    finished: Literal["none", "success", "failure"]


class FeedbackStatus(BaseModel):
    execution: Literal[
        "closed",
        "proceeding",
        "canceled",
        "scheduled",
        "rejected",
        "resumed",
        "downloaded",
        "download",
    ]
    result: FeedbackResult
    details: list[Annotated[str, StringConstraints(max_length=4096)]] = Field(
        default_factory=list, max_length=100
    )
    code: int | None = None

    @model_validator(mode="after")
    def terminal_result(self):
        if self.execution == "closed" and self.result.finished == "none":
            raise ValueError("Closed feedback requires success or failure")
        return self


class Feedback(BaseModel):
    id: str = Field(pattern=r"^[0-9]{1,20}$")
    time: str | None = Field(default=None, pattern=r"^\d{8}T\d{6}$")
    status: FeedbackStatus
