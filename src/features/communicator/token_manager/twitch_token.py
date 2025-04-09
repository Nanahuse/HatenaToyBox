import datetime

from pydantic import BaseModel, Field

# pydantic.SecretStrは保存したデータが伏せ字になるため、
# `Field(repr=False)`によって表示を抑制している。


class TwitchToken(BaseModel):
    access_token: str = Field(repr=False)
    refresh_token: str = Field(repr=False)
    scopes: str
    expires_at: datetime.datetime
