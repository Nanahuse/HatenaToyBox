import re

import flet

from .activity_control import ActivityControl


def parse_url(text: str) -> list[flet.TextSpan]:
    spans = list[flet.TextSpan]()
    last_end = 0
    for m in re.finditer(r"(https?://[A-Za-z0-9\-\._~:/\?#\[\]@!\$&'\(\)\*\+,;=%]+)", text):
        if m.start() > last_end:
            spans.append(flet.TextSpan(text=text[last_end : m.start()]))
        url = m.group(0)
        spans.append(
            flet.TextSpan(
                text=url,
                url=url,
                style=flet.TextStyle(color=flet.Colors.BLUE, decoration=flet.TextDecoration.UNDERLINE),
            )
        )
        last_end = m.end()
    if last_end < len(text):
        spans.append(flet.TextSpan(text=text[last_end:]))
    return spans


class TimeLine(flet.Column):
    def __init__(self) -> None:
        super().__init__(
            expand=True,
            scroll=flet.ScrollMode.ALWAYS,
            auto_scroll=True,
            spacing=1,
            horizontal_alignment=flet.CrossAxisAlignment.STRETCH,
        )

    def add_activity(self, who: str, text: str) -> None:
        self.controls.append(
            ActivityControl(
                who,
                parse_url(text),
                flet.Colors.with_opacity(1.0, flet.Colors.BLUE_200),
                flet.Colors.with_opacity(1.0, flet.Colors.BLUE_100),
            )
        )

    def add_clip(self, who: str, title: str, url: str) -> None:
        self.controls.append(
            ActivityControl(
                who,
                [
                    flet.TextSpan(text=f"Clip: {title} ("),
                    flet.TextSpan(
                        text=url,
                        url=url,
                        style=flet.TextStyle(color=flet.Colors.BLUE, decoration=flet.TextDecoration.UNDERLINE),
                    ),
                    flet.TextSpan(text=")"),
                ],
                flet.Colors.with_opacity(1.0, flet.Colors.ORANGE_200),
                flet.Colors.with_opacity(1.0, flet.Colors.ORANGE_100),
            )
        )

    def add_raid(self, who: str, stream_title: str, game: str) -> None:
        self.controls.append(
            ActivityControl(
                who,
                [flet.TextSpan(text=f"Raid: {stream_title} ({game})")],
                flet.Colors.with_opacity(1.0, flet.Colors.RED_200),
                flet.Colors.with_opacity(1.0, flet.Colors.RED_100),
            )
        )
