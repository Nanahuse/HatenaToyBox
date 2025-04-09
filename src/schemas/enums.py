from enum import StrEnum


class Language(StrEnum):
    JAPANESE = "ja"
    ENGLISH = "en"
    UNKNOWN = "??"


class AnnouncementColor(StrEnum):
    BLUE = "blue"
    GREEN = "green"
    ORANGE = "orange"
    PURPLE = "purple"
