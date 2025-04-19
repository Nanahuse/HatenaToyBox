import inspect
from pathlib import Path

from common.base_model import BaseEvent


class Error(BaseEvent):
    pass


class TwitchAuthenticationError(Error):
    pass


class UnhandledError(Error):
    message: str
    file_name: str
    line: int

    @classmethod
    def instance(cls, message: str) -> Error:
        try:
            stack = inspect.stack()

            if len(stack) > 1:
                caller_frame_info = stack[1]
                file_name = caller_frame_info.filename
                line_number = caller_frame_info.lineno
                return UnhandledError(message=message, file_name=Path(file_name).name, line=line_number)

            frame = inspect.currentframe()
            if frame:
                file_name = frame.f_code.co_filename
                line_number = frame.f_lineno if isinstance(frame.f_lineno, int) else -1
                return UnhandledError(message=message, file_name=Path(file_name).name, line=line_number)

        except Exception:  # noqa: BLE001, S110
            pass

        return UnhandledError(message=message, file_name="unknown", line=-1)
