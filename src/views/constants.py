from enum import StrEnum


class Route(StrEnum):
    """アプリケーションのビューを定義する列挙型"""

    MAIN = "/"
    SETTINGS = "/settings"
    CONNECTION = "/connection"
    ABOUT = "/about"
