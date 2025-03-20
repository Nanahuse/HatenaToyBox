from __future__ import annotations

import asyncio
import datetime
import json
from typing import TYPE_CHECKING, Any, Self

import aiohttp

from schemas import models

from . import constants, exceptions, responses
from .twitch_token import TwitchToken

if TYPE_CHECKING:
    from types import TracebackType


def response_to_verification(response: responses.DeviceCodeResponse) -> models.TwitchVerification:
    return models.TwitchVerification(
        device_code=response.device_code,
        interval=datetime.timedelta(seconds=response.interval),
        user_code=response.user_code,
        uri=response.verification_uri,
        expires_at=datetime.datetime.now(tz=datetime.UTC) + datetime.timedelta(seconds=response.expires_in),
    )


def response_to_token(response: responses.AccessTokenResponse, scopes: str) -> TwitchToken:
    return TwitchToken(
        access_token=response.access_token,
        refresh_token=response.refresh_token,
        scopes=scopes,
        expires_at=datetime.datetime.now(tz=datetime.UTC) + datetime.timedelta(seconds=response.expires_in),
    )


class Client:
    def __init__(self, scopes: str) -> None:
        self._session = aiohttp.ClientSession()
        self._scopes = scopes

    async def __aenter__(self) -> Self:
        await self._session.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        await self._session.__aexit__(exc_type, exc_val, exc_tb)

    async def _request[Ts: responses.Response](
        self,
        possible_models: tuple[type[Ts], ...],
        url: str,
        payload: dict[str, Any],
    ) -> Ts:
        async with self._session.post(url, data=payload) as response:
            data: dict[str, Any] = await response.json()
            data.setdefault("status", response.status)

            for model in possible_models:
                try:
                    return model.model_validate(data)
                except ValueError:
                    pass

            response.raise_for_status()

            msg = f"Unknown response error. : {json.dumps(data)}"
            raise exceptions.UnknownResponseError(msg)

    async def get_device_code(self) -> models.TwitchVerification:
        payload = {
            "client_id": constants.CLIENT_ID,
            "scopes": self._scopes,
        }

        try:
            response = await self._request(
                (responses.DeviceCodeResponse,),
                constants.DEVICE_CODE_URL,
                payload,
            )
        except Exception as e:
            raise exceptions.DeviceCodeRequestError from e

        return response_to_verification(response)

    async def get_access_token(self, verification: models.TwitchVerification) -> TwitchToken:
        payload = {
            "client_id": constants.CLIENT_ID,
            "device_code": verification.device_code,
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        }

        try:
            while datetime.datetime.now(tz=datetime.UTC) < verification.expires_at:
                response = await self._request(
                    (responses.AccessTokenResponse, responses.AuthorizationPending),
                    constants.AUTHORIZE_URL,
                    payload,
                )

                match response:
                    case responses.AccessTokenResponse():
                        return response_to_token(response, self._scopes)
                    case responses.AuthorizationPending():
                        await asyncio.sleep(verification.interval.total_seconds())

            raise exceptions.DeviceCodeExpiredError  # noqa: TRY301
        except asyncio.CancelledError:
            raise
        except Exception as e:
            raise exceptions.AuthorizationError from e

    async def refresh_access_token(self, refresh_token: str) -> TwitchToken:
        payload = {
            "client_id": constants.CLIENT_ID,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }

        try:
            response = await self._request(
                (responses.AccessTokenResponse,),
                constants.AUTHORIZE_URL,
                payload,
            )
        except Exception as e:
            raise exceptions.AuthorizationError from e

        return response_to_token(response, self._scopes)
