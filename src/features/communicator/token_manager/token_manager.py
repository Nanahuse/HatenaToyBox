from __future__ import annotations

import asyncio
import contextlib
import datetime
from typing import TYPE_CHECKING

from schemas import models
from utils import routines
from utils.model_file import ModelFile

from . import exceptions
from .client import Client
from .twitch_token import TwitchToken

if TYPE_CHECKING:
    import logging
    from collections.abc import Awaitable, Callable
    from pathlib import Path

TOKEN_EXPIRE_MARGIN = datetime.timedelta(minutes=10)
TOKEN_CHECK_INTERVAL = datetime.timedelta(minutes=5)


class TokenManager:
    def __init__(  # noqa: PLR0913
        self,
        logger: logging.Logger,
        name: str,
        scopes: list[str],
        token_file_directory: Path,
        start_verification_callback: Callable[[models.TwitchVerification], Awaitable[None]],
        token_update_callback: Callable[[models.Token], Awaitable[None]],
    ) -> None:
        self._logger = logger.getChild(self.__class__.__name__).getChild(name)

        self._name = name
        self._scopes = " ".join(scopes)
        self._update_routine: routines.Routine | None = None

        self._token_file = ModelFile(TwitchToken, token_file_directory / f"token_{name}.json", self._logger)
        if self._token_file.data is not None and self._token_file.data.scopes != self._scopes:
            self._token_file.clear()

        self._start_verification = start_verification_callback
        self._token_update_callback = token_update_callback

    @property
    def _token(self) -> TwitchToken | None:
        return self._token_file.data

    def _get_valid_token(self) -> TwitchToken | None:
        if self._token is None:
            return None

        if self._token.expires_at <= datetime.datetime.now(tz=datetime.UTC) + TOKEN_EXPIRE_MARGIN:
            return None

        return self._token

    async def run(self) -> None:
        self._logger.debug("Starting")

        if (token := self._get_valid_token()) is not None:
            await self._update_token("Token loaded from file.", token)

        self._update_routine = routines.routine(seconds=TOKEN_CHECK_INTERVAL.total_seconds())(self._refresh_token)

        with contextlib.suppress(asyncio.CancelledError):
            await self._update_routine.start()

    async def close(self) -> None:
        self._logger.debug("Stopping")
        if not self.is_running:
            return

        update_routine, self._update_routine = self._update_routine, None

        if update_routine is not None:
            update_routine.cancel()

        self._logger.debug("Stopped")

    def clear(self) -> None:
        self._logger.debug("Clearing token")
        if self._token_file.data is not None:
            self._token_file.clear()

        if self._update_routine is not None:
            self._update_routine.restart()

    @property
    def is_running(self) -> bool:
        return self._update_routine is not None

    async def _refresh_token(self) -> None:
        if (token := self._get_valid_token()) is not None:
            self._logger.debug("Token is still valid. expires at %s", token.expires_at.astimezone())
            return

        async with Client(self._scopes) as client:
            if self._token is not None:
                try:
                    token = await client.refresh_access_token(self._token.refresh_token)
                    await self._update_token("Token refreshed successfully.", token)
                    return
                except exceptions.AuthorizationError:
                    self._logger.debug("Failed to refresh token.")

            self._logger.debug("Getting new token.")

            try:
                device_code = await client.get_device_code()
                await self._start_verification(device_code)

                access_token = await client.get_access_token(device_code)
                await self._update_token("New Token acquired.", access_token)
                return
            except exceptions.AuthorizationError:
                self._logger.exception("Failed to get new token.")

    async def _update_token(self, message: str, token: TwitchToken) -> None:
        self._logger.info("%s : expires at %s", message, token.expires_at.astimezone())
        self._token_file.update(token)
        await self._token_update_callback(
            models.Token(name=self._name, access_token=token.access_token),
        )
