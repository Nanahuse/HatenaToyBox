import flet

from .color_dropdown import ColorDropdown


class MessageFormatRow(flet.Row):  # type:ignore[misc]
    """メッセージ形式設定のためのTextField, (オプションの)ColorDropdown, TestButtonを持つRow"""

    def __init__(
        self,
        value: str,
        width: int,
        show_color_dropdown: bool = False,  # noqa: FBT001, FBT002
    ) -> None:
        self.text_field = flet.TextField(label="メッセージの形式", value=value, multiline=False, expand=True)
        controls = [self.text_field]
        self.color_dropdown = None
        if show_color_dropdown:
            self.color_dropdown = ColorDropdown(width=width)
            controls.append(self.color_dropdown)

        self.test_button = flet.Button(text="テスト", width=width)
        controls.append(self.test_button)

        super().__init__(controls=controls)

    @property
    def value(self) -> str | None:
        return self.text_field.value  # type: ignore[no-any-return]

    @value.setter
    def value(self, new_value: str | None) -> None:
        self.text_field.value = new_value

    @property
    def color(self) -> str | None:
        return self.color_dropdown.value if self.color_dropdown else None

    @color.setter
    def color(self, new_value: str | None) -> None:
        if self.color_dropdown:
            self.color_dropdown.value = new_value
