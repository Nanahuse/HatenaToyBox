from typing import Literal

from pydantic import BaseModel


class TranslatorConfig(BaseModel):
    type: str


class GoogleConfig(TranslatorConfig):
    type: Literal["google"]


class DeeplConfig(TranslatorConfig):
    type: Literal["deepl"]
    api_key: str
