from enum import Enum

import flet


class ConnectionStatus(Enum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"


class ConnectionStatusColor:
    CONNECTED = flet.Colors.GREEN
    DISCONNECTED = flet.Colors.RED
    CONNECTING = flet.Colors.ORANGE


# --- 接続状態アイコンの定数を追加 ---
class ConnectionStatusIcon:
    CONNECTED = flet.Icons.LINK_OUTLINED
    DISCONNECTED = flet.Icons.LINK_OFF_OUTLINED
    CONNECTING = flet.Icons.HOURGLASS_EMPTY_OUTLINED


class ConnectionIndicator(flet.IconButton):  # type: ignore[misc]
    def __init__(self) -> None:
        super().__init__(icon_size=30)

        self.update_status(ConnectionStatus.DISCONNECTED)  # 初期状態は未接続

    def update_status(self, status: ConnectionStatus) -> None:
        """接続状態に基づいてアイコンと色、ツールチップを更新する"""
        match status:
            case ConnectionStatus.CONNECTED:
                self.icon = ConnectionStatusIcon.CONNECTED
                self.icon_color = ConnectionStatusColor.CONNECTED
                self.tooltip = "接続済み"
            case ConnectionStatus.CONNECTING:
                self.icon = ConnectionStatusIcon.CONNECTING
                self.icon_color = ConnectionStatusColor.CONNECTING
                self.tooltip = "接続中..."
            case ConnectionStatus.DISCONNECTED:
                self.icon = ConnectionStatusIcon.DISCONNECTED
                self.icon_color = ConnectionStatusColor.DISCONNECTED
                self.tooltip = "未接続"
