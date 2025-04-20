import inspect
from unittest.mock import MagicMock, patch

from schemas.errors import UnhandledError

# --- UnhandledError.instance() ---


def test_unhandled_error_instance_creation_success() -> None:
    """UnhandledError.instance() が呼び出し元の情報を正しく取得してインスタンスを生成することを確認します。
    (注: errors.py の instance() が inspect.stack() を使うように修正されている前提)
    """
    test_message = "Error occurred here"
    # この行で instance() が呼ばれる
    error_instance = UnhandledError.instance(test_message)
    current_frame = inspect.currentframe()
    assert current_frame is not None
    current_line = current_frame.f_lineno - 3  # instance() を呼び出した行 構造を変えると番号も変わる。

    assert isinstance(error_instance, UnhandledError)
    assert error_instance.message == test_message
    # inspect.stack() が呼び出し元 (このテストファイル) の情報を取得することを期待
    assert error_instance.file_name == "test_errors.py"
    assert error_instance.line == current_line


def test_unhandled_error_instance_creation_stack_too_short() -> None:
    """UnhandledError.instance() が inspect.stack() が短い場合のフォールバックを確認します。"""
    test_message = "Error with short stack"
    # inspect.stack をモックして短いスタック (長さ1) を返すようにする
    mock_frame_info = MagicMock(spec=inspect.FrameInfo)
    mock_frame_info.filename = "/path/to/errors.py"  # instance() 自身のファイル
    mock_frame_info.lineno = 50  # ダミーの行番号
    # stack() が短い場合、errors.py の実装では currentframe() を試みる
    # currentframe() が成功した場合のテスト
    with patch("schemas.errors.inspect.stack", return_value=[mock_frame_info]):
        # currentframe() はモックしないので、errors.py 内のフレームが取得されるはず
        error_instance = UnhandledError.instance(test_message)

    assert isinstance(error_instance, UnhandledError)
    assert error_instance.message == test_message
    # フォールバックで currentframe() が使われ、errors.py の情報が取得される
    assert error_instance.file_name == "errors.py"
    assert isinstance(error_instance.line, int)
    assert error_instance.line > 0  # errors.py 内の具体的な行番号


def test_unhandled_error_instance_creation_currentframe_none() -> None:
    """UnhandledError.instance() が inspect.currentframe() も None を返す場合の最終フォールバックを確認します。"""
    test_message = "Error with no frame info"
    # stack() が短く、かつ currentframe() も None を返す状況
    mock_frame_info = MagicMock(spec=inspect.FrameInfo)
    mock_frame_info.filename = "/path/to/errors.py"
    mock_frame_info.lineno = 50
    with (
        patch("schemas.errors.inspect.stack", return_value=[mock_frame_info]),
        patch("schemas.errors.inspect.currentframe", return_value=None),
    ):
        error_instance = UnhandledError.instance(test_message)

    assert isinstance(error_instance, UnhandledError)
    assert error_instance.message == test_message
    # 最終フォールバック
    assert error_instance.file_name == "unknown"
    assert error_instance.line == -1


def test_unhandled_error_instance_creation_inspect_exception() -> None:
    """UnhandledError.instance() が inspect 中の例外発生時のフォールバックを確認します。"""
    test_message = "Error during inspection"
    # inspect.stack をモックして例外を発生させる
    with patch("schemas.errors.inspect.stack", side_effect=RuntimeError("Inspect failed")):
        error_instance = UnhandledError.instance(test_message)

    assert isinstance(error_instance, UnhandledError)
    assert error_instance.message == test_message
    # 例外発生時のフォールバック
    assert error_instance.file_name == "unknown"
    assert error_instance.line == -1
