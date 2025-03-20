from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, override

from common.feature import ConfigData, Feature
from schemas import events, models, services
from schemas.enums import Language
from utils import routines
from utils.resizable_queue import ResizableQueue

from .config import SystemConfig, UserConfig
from .language_identification import IdentifierAdaptor, JapaneseIdentifier
from .translator_adaptor import DeeplTranslator, GoogleTranslator, TranslationError, translator_config

if TYPE_CHECKING:
    from common.core import Hub

    from .translator_adaptor import TranslatorAdaptor

TRANSLATION_INTERVAL = datetime.timedelta(seconds=1)


class MessageTranslator(Feature[SystemConfig, UserConfig]):
    def __init__(self, hub: Hub, system_config: ConfigData) -> None:
        super().__init__(hub, SystemConfig, UserConfig, system_config)
        self._event_publisher = hub.create_publisher()
        self._service_caller = hub.create_caller()

        self._message_queue = ResizableQueue[events.MessageFiltered]()

        self._translator: TranslatorAdaptor | None = None
        self._identifier: IdentifierAdaptor | None = None

        hub.add_event_handler(events.MessageFiltered, self._message_queue.put)

    @override
    async def set_user_config(self, config: ConfigData | None) -> bool:
        result = await super().set_user_config(config)
        if not result:
            return False

        self._translator = None

        if self.user_config is None:
            return True

        match self.user_config.translator:
            case translator_config.GoogleConfig():
                self._translator = GoogleTranslator(
                    self.logger,
                    self.system_config.cache_directory,
                    self.system_config.cache_max,
                    self.user_config.translator,
                )
            case translator_config.DeeplConfig():
                self._translator = DeeplTranslator(
                    self.logger,
                    self.system_config.cache_directory,
                    self.system_config.cache_max,
                    self.user_config.translator,
                )
            case _:
                msg = f"Unknown translator: {self.user_config.translator.type}"
                raise ValueError(msg)

        if self.user_config.first_language == Language.JAPANESE:
            self._identifier = JapaneseIdentifier()
        else:
            self._identifier = IdentifierAdaptor()

        self._message_queue.change_maxsize(self.user_config.queue_max)
        return True

    @override
    async def run(self) -> None:
        routine_manager = routines.RoutineManager()
        routine_manager.add(self._main, TRANSLATION_INTERVAL)

        routine_manager.start()
        await super().run()
        routine_manager.clear()

    async def _main(self) -> None:
        event = await self._message_queue.get()

        if self.user_config is None:
            return  # Not initialized yet.

        if self._translator is None:
            msg = "Translator is not initialized."
            raise RuntimeError(msg)

        if self._identifier is None:
            msg = "Language identifier is not initialized."
            raise RuntimeError(msg)

        if self.user_config.ignore_emote_only_message and all(
            isinstance(part, models.Emote) for part in event.message.parsed_content
        ):
            self.logger.debug("Ignore emote only translation.")
            return

        language = self._identifier.identify(event.message.content)

        translate_to = (
            self.user_config.second_language
            if language == self.user_config.first_language
            else self.user_config.first_language
        )

        try:
            translated_contents: list[str | models.Emote] = [
                await self._translator.translate(raw, translate_to, language) if isinstance(raw, str) else raw
                for raw in event.message.parsed_content
            ]
        except TranslationError:
            self.logger.exception("Translate Failed")
            return

        translated = models.Message(
            content=" ".join(part.text if isinstance(part, models.Emote) else part for part in translated_contents),
            parsed_content=translated_contents,
            author=event.message.author,
            is_echo=event.message.is_echo,
        )

        await self._event_publisher.publish(events.MessageTranslated(message=translated))

        if self.user_config.do_comment:
            content = (
                self.user_config.message_format.replace("{author}", event.message.author.name)
                .replace("{from}", language.value)
                .replace("{to}", translate_to.value)
                .replace("{message}", translated.content)
            )
            await self._service_caller.call(
                services.SendComment(
                    payload=models.Comment(
                        content=content,
                        is_italic=True,
                    ),
                ),
            )
