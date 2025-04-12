from enum import IntEnum
from typing import Literal

from pydantic import BaseModel


class StatusCode(IntEnum):
    Success = 200
    Error = 400


class Response(BaseModel):
    status: StatusCode


class DeviceCodeResponse(Response):
    status: Literal[StatusCode.Success]
    device_code: str
    expires_in: int
    interval: int
    user_code: str
    verification_uri: str


class AccessTokenResponse(Response):
    status: Literal[StatusCode.Success]
    access_token: str
    expires_in: int
    refresh_token: str
    scope: list[str]
    token_type: str


class AuthorizationPending(Response):
    status: Literal[StatusCode.Error]
    message: Literal["authorization_pending"]
