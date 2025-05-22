import flet

from .constants import Route
from .controls.file_picker_row import FilePickerRow
from .controls.message_format_row import MessageFormatRow
from .controls.volume_slider_row import VolumeSliderRow
from .header import Header
from .router import Router

WIDTH = 120


# --- セクションクラス ---


class ConnectionSettingsSection(flet.Column):  # type: ignore[misc]
    """Connection設定セクション"""

    def __init__(self, router: Router) -> None:
        # --- コントロール ---
        self.account_settings_button = flet.Button(
            "アカウントの設定",
            width=200,
            on_click=lambda _: router.go_connection(),
        )
        self.channel_field = flet.TextField(label="接続先チャンネル", multiline=False, width=400)

        super().__init__(
            controls=[
                flet.Text("Connection", style=flet.TextThemeStyle.HEADLINE_SMALL),
                self.account_settings_button,
                self.channel_field,
            ]
        )


class ChatSettingsSection(flet.Column):  # type: ignore[misc]
    """Chatの設定セクション"""

    class DoorbellSubSection(flet.Column):  # type: ignore[misc]
        """ドアベル設定セクション"""

        def __init__(self, router: Router) -> None:
            # --- コントロール ---
            self.switch = flet.Switch(
                label="新規チャット参加者にドアベルを鳴らす",
                tooltip="その日初めてのチャットに反応して音を鳴らします",
                value=True,
                on_change=self._on_change,
            )
            self.file_picker = FilePickerRow(
                page=router.page,
                label="SEファイル",
                file_type=flet.FilePickerFileType.AUDIO,
                width=WIDTH,
            )
            self.volume_slider = VolumeSliderRow(value=50)

            super().__init__(
                controls=[
                    self.switch,
                    self.file_picker,
                    self.volume_slider,
                ]
            )

        def _on_change(self, _: flet.ControlEvent) -> None:
            self.file_picker.visible = self.switch.value
            self.volume_slider.visible = self.switch.value
            self.update()

    class TranslateSubSection(flet.Column):  # type: ignore[misc]
        """翻訳設定セクション"""

        def __init__(self, _router: Router) -> None:
            # --- コントロール ---
            self.switch = flet.Switch(
                label="チャットを翻訳",
                tooltip="日本語を英語、日本語以外は日本語に",
                value=True,
                on_change=self._on_change,
            )
            self.message_format = MessageFormatRow(
                value="[{author}]{message}({from}->{to})",
                show_color_dropdown=False,
                width=WIDTH,
            )
            self.api_dropdown = flet.Dropdown(
                label="翻訳API",
                options=[flet.dropdown.Option("Google"), flet.dropdown.Option("DeepL")],
                value="Google",
                width=150,
                on_change=self._on_api_change,
            )

            self.api_key_field = flet.TextField(label="APIキー", value="", multiline=False, expand=True, disabled=True)

            self.api_row = flet.Row(
                controls=[
                    self.api_dropdown,
                    self.api_key_field,
                ]
            )

            super().__init__(
                controls=[
                    self.switch,
                    self.api_row,
                ]
            )

        def _on_change(self, _: flet.ControlEvent) -> None:
            self.message_format.visible = self.switch.value
            self.api_row.visible = self.switch.value
            self.update()

        def _on_api_change(self, _: flet.ControlEvent) -> None:
            self.api_key_field.disabled = self.api_dropdown.value == "Google"
            self.api_key_field.update()

    def __init__(self, router: Router) -> None:
        self.ignored_users_field = flet.TextField(label="反応しないユーザー", multiline=True)
        self.doorbell_settings = self.DoorbellSubSection(router)
        self.translate_settings = self.TranslateSubSection(router)

        super().__init__(
            controls=[
                flet.Text("Chat", style=flet.TextThemeStyle.HEADLINE_SMALL),
                self.ignored_users_field,
                self.doorbell_settings,
                self.translate_settings,
            ]
        )


class RaidSettingsSection(flet.Column):  # type: ignore[misc]
    """Raid設定セクション"""

    def __init__(self, _router: Router) -> None:
        self.shoutout_switch = flet.Switch(label="シャウトアウトする", value=True, on_change=self._on_change)
        self.introduce_switch = flet.Switch(label="チャットで紹介する", value=True, on_change=self._on_change)
        self.message_format = MessageFormatRow(
            value="",
            show_color_dropdown=True,
            width=WIDTH,
        )
        self.wait_time_slider = flet.Slider(label="{value}秒", min=0, max=20, value=5, divisions=20, expand=True)

        self.wait_time_slider_row = flet.Row(
            [
                flet.Text("応答待ち時間", tooltip="Raidからの視聴者が揃うまで応答を遅らせます"),
                self.wait_time_slider,
            ],
        )

        super().__init__(
            controls=[
                flet.Text("Raid", style=flet.TextThemeStyle.HEADLINE_SMALL),
                self.shoutout_switch,
                self.introduce_switch,
                self.message_format,
                self.wait_time_slider_row,
            ]
        )

    def _on_change(self, _: flet.ControlEvent) -> None:
        self.wait_time_slider_row.visible = self.shoutout_switch.value or self.introduce_switch.value
        self.message_format.visible = self.introduce_switch.value
        self.update()


class ClipSettingsSection(flet.Column):  # type: ignore[misc]
    """Clip設定セクション"""

    def __init__(self, _router: Router) -> None:
        # --- コントロール ---
        self.clip_introduce_switch = flet.Switch(label="チャットで紹介する", on_change=self._on_change, value=True)
        self.clip_message_format = MessageFormatRow(
            value="",
            show_color_dropdown=True,
            width=WIDTH,
        )

        self.clip_message_format.test_button.on_click = lambda _: print(self.clip_message_format.text_field.value)

        super().__init__(
            controls=[
                flet.Text("Clip", style=flet.TextThemeStyle.HEADLINE_SMALL),
                self.clip_introduce_switch,
                self.clip_message_format,
            ]
        )

    def _on_change(self, _: flet.ControlEvent) -> None:
        self.clip_message_format.visible = self.clip_introduce_switch.value
        self.update()


class StreamInfoSettingsSection(flet.Column):  # type: ignore[misc]
    """StreamInfo設定セクション"""

    def __init__(self, _router: Router) -> None:
        self.switch = flet.Switch(
            label="配信情報の管理",
            value=True,
            tooltip="コマンドで配信情報を変更できるようになります。",
        )

        super().__init__(controls=[flet.Text("Stream Info", style=flet.TextThemeStyle.HEADLINE_SMALL), self.switch])


# --- 設定ページのクラス ---
class SettingView:
    def __init__(self, router: Router) -> None:
        """SettingsPageクラスの初期化"""
        self.padding = 10

        self.header = Header(router, "設定")
        self.connection_settings_section = ConnectionSettingsSection(router)
        self.chat_settings_section = ChatSettingsSection(router)
        self.raid_settings_section = RaidSettingsSection(router)
        self.clip_settings_section = ClipSettingsSection(router)
        self.stream_info_section = StreamInfoSettingsSection(router)

    def build_view(self) -> flet.View:
        """設定ページのViewを構築して返す"""

        return flet.View(
            Route.SETTINGS,
            controls=[
                self.header,
                self.connection_settings_section,
                flet.Divider(height=1),
                self.chat_settings_section,
                flet.Divider(height=1),
                self.raid_settings_section,
                flet.Divider(height=1),
                self.clip_settings_section,
                flet.Divider(height=1),
                self.stream_info_section,
                flet.Divider(height=1),
            ],
            vertical_alignment=flet.MainAxisAlignment.START,
            horizontal_alignment=flet.CrossAxisAlignment.STRETCH,
            padding=self.padding,  # mainで設定したpaddingを適用
            scroll=flet.ScrollMode.ALWAYS,
        )
