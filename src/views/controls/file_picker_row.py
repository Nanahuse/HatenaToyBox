import flet


class FilePickerRow(flet.Row):  # type: ignore[misc]
    """ファイル選択のためのTextFieldとButtonを持つRow"""

    def __init__(
        self,
        page: flet.Page,
        label: str,
        file_type: flet.FilePickerFileType,
        width: int | None = None,
        value: str | None = None,
    ) -> None:
        self.text_field = flet.TextField(label=label, value=value, multiline=False, expand=True)
        self.button = flet.Button(text="選択", width=width, on_click=self.file_picker_click)
        self.file_picker = flet.FilePicker(on_result=self.file_picker_result)
        self.file_type = file_type
        page.overlay.append(self.file_picker)
        super().__init__(controls=[self.text_field, self.button])

    @property
    def value(self) -> str | None:
        return self.text_field.value  # type: ignore[no-any-return]

    @value.setter
    def value(self, new_value: str | None) -> None:
        self.text_field.value = new_value

    def file_picker_click(self, _: flet.ControlEvent) -> None:
        self.file_picker.pick_files(file_type=self.file_type, allow_multiple=False)

    def file_picker_result(self, e: flet.FilePickerResultEvent) -> None:
        if not e.files:
            return
        self.text_field.value = e.files[0].path
        self.update()
