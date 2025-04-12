import inspect
from pathlib import Path

from common.base_model import BaseEvent

from .enums import Language


class Error(BaseEvent):
    def what(self, lang: Language) -> str:
        raise NotImplementedError(type(self).__name__)


class TwitchAuthenticationError(Error):
    def what(self, lang: Language) -> str:
        match lang:
            case Language.JAPANESE:
                return "Twitchのログインに失敗しました。API tokenを確認してください。"
        return super().what(lang)


class TwitchUnauthorizedError(Error):
    where: str
    message: str

    def what(self, lang: Language) -> str:
        match lang:
            case Language.JAPANESE:
                return f"Twitchへのアクセス権が不足しています。API tokenを再取得してください。[{self.where}]:{self.message}"  # noqa: E501
        return super().what(lang)


class TwitchConnectionError(Error):
    channel: str

    def what(self, lang: Language) -> str:
        match lang:
            case Language.JAPANESE:
                return f"Twitch:{self.channel} への接続に失敗しました。"
        return super().what(lang)


class TwitchShoutoutError(Error):
    message: str

    def what(self, lang: Language) -> str:
        match lang:
            case Language.JAPANESE:
                return f"Twitch:シャウトアウトに失敗しました。{self.message}"
        return super().what(lang)


class TwitchStreamInfoModifyError(Error):
    message: str

    def what(self, lang: Language) -> str:
        match lang:
            case Language.JAPANESE:
                return f"Twitch:配信情報の編集に失敗しました。{self.message}"
        return super().what(lang)


class SoundFileNotFoundError(Error):
    path: Path

    def what(self, lang: Language) -> str:
        match lang:
            case Language.JAPANESE:
                return f"サウンドファイルが見つかりません。: path={self.path.absolute()!s}"
        return super().what(lang)


class TranslationFailedError(Error):
    message: str

    def what(self, lang: Language) -> str:
        match lang:
            case Language.JAPANESE:
                return f"翻訳に失敗しました。: {self.message}"
        return super().what(lang)


class UnhandledError(Error):
    message: str
    file_name: str
    line: int

    def what(self, lang: Language) -> str:
        match lang:
            case Language.JAPANESE:
                return f"制作者に詳細をご連絡ください。詳細: {self.message} [{self.file_name}:{self.line}]"
        return super().what(lang)

    @classmethod
    def instance(cls, message: str) -> Error:
        frame = inspect.currentframe()

        if frame is None:
            return UnhandledError(message=message, file_name="unknown", line=-1)

        file_name = frame.f_code.co_filename
        path = Path(file_name)

        line_number = frame.f_lineno if isinstance(frame.f_lineno, int) else -1
        return UnhandledError(message=message, file_name=path.name, line=line_number)
