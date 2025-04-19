# test/features/message_translator/test_message_translator.py

import asyncio
from collections.abc import Generator
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from common.feature import ConfigData, Feature
from features.message_translator.config import SystemConfig, UserConfig
from features.message_translator.message_translator import TRANSLATION_INTERVAL, MessageTranslator
from features.message_translator.translator_adaptor import TranslationError
from schemas import events, models, services
from schemas.enums import Language
from utils.resizable_queue import ResizableQueue

# --- テスト用定数 ---
CACHE_MAX_SIZE = 100
QUEUE_MAX_SIZE = 50
TEST_CACHE_DIR = Path("/fake/cache/dir")
TEST_MESSAGE_FORMAT = "{author}: {message} ({from} -> {to})"

# --- フィクスチャ ---


@pytest.fixture
def mock_hub() -> MagicMock:
    """モックされた Hub インスタンスを提供します。"""
    hub = MagicMock(spec=["create_publisher", "create_caller", "add_event_handler"])
    hub.create_publisher.return_value = AsyncMock()
    hub.create_caller.return_value = AsyncMock()
    hub.add_event_handler = MagicMock()
    return hub


@pytest.fixture
def mock_event_publisher(mock_hub: MagicMock) -> AsyncMock:
    """モックされた EventPublisher インスタンスを提供します。"""
    return cast("AsyncMock", mock_hub.create_publisher.return_value)


@pytest.fixture
def mock_service_caller(mock_hub: MagicMock) -> AsyncMock:
    """モックされた ServiceCaller インスタンスを提供します。"""
    return cast("AsyncMock", mock_hub.create_caller.return_value)


@pytest.fixture
def mock_system_config_data() -> ConfigData:
    """モックされた SystemConfig データを提供します。"""
    # 実際の ConfigData 形式に合わせて辞書を作成
    return {
        "version": 0,
        "cache_max": CACHE_MAX_SIZE,
        "cache_directory": str(TEST_CACHE_DIR),  # Path オブジェクトは JSON にできないため文字列
    }


@pytest.fixture
def mock_system_config(mock_system_config_data: ConfigData) -> SystemConfig:
    """SystemConfig のインスタンスを提供します。"""
    # SystemConfig.model_validate を使用してインスタンス化
    return SystemConfig.model_validate(mock_system_config_data)


# --- UserConfig フィクスチャ (パラメータ化用) ---
@pytest.fixture(
    params=[
        # Google Translator ケース
        {
            "version": 0,
            "first_language": Language.JAPANESE,
            "second_language": Language.ENGLISH,
            "do_comment": True,
            "message_format": TEST_MESSAGE_FORMAT,
            "queue_max": QUEUE_MAX_SIZE,
            "ignore_emote_only_message": True,
            "translator": {"type": "google"},
        },
        # Deepl Translator ケース
        {
            "version": 0,
            "first_language": Language.ENGLISH,
            "second_language": Language.JAPANESE,
            "do_comment": False,
            "message_format": "{message}",
            "queue_max": QUEUE_MAX_SIZE + 10,
            "ignore_emote_only_message": False,
            "translator": {"type": "deepl", "api_key": "fake-deepl-key"},
        },
    ]
)
def mock_user_config_data(request: pytest.FixtureRequest) -> ConfigData:
    """パラメータ化された UserConfig データを提供します。"""
    return cast("ConfigData", request.param)


@pytest.fixture
def mock_user_config(mock_user_config_data: ConfigData) -> UserConfig:
    """UserConfig のインスタンスを提供します。"""
    return UserConfig.model_validate(mock_user_config_data)


# --- 依存クラスのモック用フィクスチャ ---


@pytest.fixture
def mock_resizable_queue_instance() -> MagicMock:
    """モックされた ResizableQueue インスタンスを作成し、設定します。"""
    instance = MagicMock(spec=ResizableQueue)  # spec に元のクラスを指定
    instance.get = AsyncMock()
    instance.put = MagicMock()
    instance.change_maxsize = MagicMock()
    return instance


@pytest.fixture(autouse=True)
def mock_google_translator_cls() -> Generator[MagicMock, None, None]:
    """GoogleTranslator クラスをモックします。"""
    patcher = patch("features.message_translator.message_translator.GoogleTranslator", autospec=True)
    mock_cls = patcher.start()
    # translate メソッドを AsyncMock にする
    mock_cls.return_value.translate = AsyncMock(return_value="translated_google")
    yield mock_cls
    patcher.stop()


@pytest.fixture
def mock_google_translator_instance(mock_google_translator_cls: MagicMock) -> MagicMock:
    """モックされた GoogleTranslator インスタンスを提供します。"""
    return cast("MagicMock", mock_google_translator_cls.return_value)


@pytest.fixture(autouse=True)
def mock_deepl_translator_cls() -> Generator[MagicMock, None, None]:
    """DeeplTranslator クラスをモックします。"""
    patcher = patch("features.message_translator.message_translator.DeeplTranslator", autospec=True)
    mock_cls = patcher.start()
    # translate メソッドを AsyncMock にする
    mock_cls.return_value.translate = AsyncMock(return_value="translated_deepl")
    yield mock_cls
    patcher.stop()


@pytest.fixture
def mock_deepl_translator_instance(mock_deepl_translator_cls: MagicMock) -> MagicMock:
    """モックされた DeeplTranslator インスタンスを提供します。"""
    return cast("MagicMock", mock_deepl_translator_cls.return_value)


@pytest.fixture(autouse=True)
def mock_japanese_identifier_cls() -> Generator[MagicMock, None, None]:
    """JapaneseIdentifier クラスをモックします。"""
    patcher = patch("features.message_translator.message_translator.JapaneseIdentifier", autospec=True)
    mock_cls = patcher.start()
    # identify メソッドを設定
    mock_cls.return_value.identify = MagicMock(return_value=Language.JAPANESE)
    yield mock_cls
    patcher.stop()


@pytest.fixture
def mock_japanese_identifier_instance(mock_japanese_identifier_cls: MagicMock) -> MagicMock:
    """モックされた JapaneseIdentifier インスタンスを提供します。"""
    return cast("MagicMock", mock_japanese_identifier_cls.return_value)


@pytest.fixture(autouse=True)
def mock_identifier_adaptor_cls() -> Generator[MagicMock, None, None]:
    """IdentifierAdaptor クラスをモックします。"""
    patcher = patch("features.message_translator.message_translator.IdentifierAdaptor", autospec=True)
    mock_cls = patcher.start()
    # identify メソッドを設定
    mock_cls.return_value.identify = MagicMock(return_value=Language.UNKNOWN)  # デフォルトは UNKNOWN
    yield mock_cls
    patcher.stop()


@pytest.fixture
def mock_identifier_adaptor_instance(mock_identifier_adaptor_cls: MagicMock) -> MagicMock:
    """モックされた IdentifierAdaptor インスタンスを提供します。"""
    return cast("MagicMock", mock_identifier_adaptor_cls.return_value)


@pytest.fixture(autouse=True)
def mock_routine_manager_cls() -> Generator[MagicMock, None, None]:
    """routines.RoutineManager クラスをモックします。"""
    patcher = patch("features.message_translator.message_translator.routines.RoutineManager", autospec=True)
    mock_cls = patcher.start()
    yield mock_cls
    patcher.stop()


@pytest.fixture
def mock_routine_manager_instance(mock_routine_manager_cls: MagicMock) -> MagicMock:
    """モックされた RoutineManager インスタンスを提供します。"""
    return cast("MagicMock", mock_routine_manager_cls.return_value)


@pytest.fixture
def translator_feature(
    mock_hub: MagicMock,
    mock_system_config_data: ConfigData,
    mock_resizable_queue_instance: MagicMock,  # 事前に作成したインスタンスを要求
    # 以下のモックは autouse=True なので自動的に適用される
    mock_google_translator_cls: MagicMock,  # noqa: ARG001
    mock_deepl_translator_cls: MagicMock,  # noqa: ARG001
    mock_japanese_identifier_cls: MagicMock,  # noqa: ARG001
    mock_identifier_adaptor_cls: MagicMock,  # noqa: ARG001
    mock_routine_manager_cls: MagicMock,  # noqa: ARG001
) -> Generator[MessageTranslator, None, None]:
    """テスト対象の MessageTranslator インスタンスを提供します。"""
    # patch を使用して ResizableQueue クラス自体をモックする
    with patch("features.message_translator.message_translator.ResizableQueue") as mock_resizable_queue_class:
        # クラスモックの __getitem__ が呼ばれたときに返すモック (mock_getitem_result) を作成
        mock_getitem_result = MagicMock()
        mock_getitem_result.return_value = mock_resizable_queue_instance
        mock_resizable_queue_class.__getitem__ = MagicMock(return_value=mock_getitem_result)
        yield MessageTranslator(mock_hub, mock_system_config_data)


# --- テストケース ---


def test_initialization(
    translator_feature: MessageTranslator,
    mock_hub: MagicMock,
    mock_system_config: SystemConfig,
    mock_resizable_queue_instance: MagicMock,  # インスタンスを直接使用
) -> None:
    """MessageTranslator が正しく初期化されるかをテストします。"""
    # Hub メソッドの呼び出し確認
    mock_hub.create_publisher.assert_called_once()
    mock_hub.create_caller.assert_called_once()
    # add_event_handler のコールバックがモックインスタンスの put であることを確認
    mock_hub.add_event_handler.assert_called_once_with(events.MessageFiltered, mock_resizable_queue_instance.put)

    # ResizableQueue の初期化確認 - patch の return_value を使ったため、
    # 呼び出し自体の確認は translator_feature フィクスチャ内の patch で行われる。
    # ここでは、インスタンスが正しく設定されたかを確認する。

    # 初期状態の確認
    assert translator_feature._translator is None
    assert translator_feature._identifier is None
    assert translator_feature._event_publisher is mock_hub.create_publisher.return_value
    assert translator_feature._service_caller is mock_hub.create_caller.return_value
    assert translator_feature._message_queue is mock_resizable_queue_instance  # モックインスタンスであることを確認

    # SystemConfig の確認
    assert translator_feature.system_config.cache_max == mock_system_config.cache_max
    assert translator_feature.system_config.cache_directory == mock_system_config.cache_directory


@pytest.mark.asyncio
async def test_set_user_config_none(translator_feature: MessageTranslator) -> None:
    """ユーザー設定が None の場合に正しく処理されるかをテストします。"""
    await translator_feature.set_user_config(
        {
            "version": 0,
            "first_language": Language.ENGLISH,
            "second_language": Language.JAPANESE,
            "do_comment": False,
            "message_format": "{message}",
            "ignore_emote_only_message": False,
            "translator": {"type": "google"},
            "queue_max": 10,
        }
    )
    assert translator_feature._translator is not None

    # None を設定
    result = await translator_feature.set_user_config(None)

    assert result is True
    assert translator_feature.user_config is None
    assert translator_feature._translator is None
    assert translator_feature._identifier is None


@pytest.mark.asyncio
async def test_set_user_config_same_config(translator_feature: MessageTranslator) -> None:
    """ユーザー設定が None の場合に正しく処理されるかをテストします。"""
    # None を設定
    await translator_feature.set_user_config(None)

    result = await translator_feature.set_user_config(None)

    assert result is False


@pytest.mark.asyncio
async def test_set_user_config_google(
    translator_feature: MessageTranslator,
    mock_system_config: SystemConfig,
    mock_google_translator_cls: MagicMock,
    mock_identifier_adaptor_cls: MagicMock,  # first_language が EN の場合
    mock_resizable_queue_instance: MagicMock,
) -> None:
    """Google Translator のユーザー設定が正しく適用されるかをテストします。"""
    google_config_data: ConfigData = {
        "version": 0,
        "first_language": Language.ENGLISH,  # IdentifierAdaptor を期待
        "second_language": Language.JAPANESE,
        "do_comment": True,
        "message_format": "test",
        "queue_max": QUEUE_MAX_SIZE,
        "ignore_emote_only_message": False,
        "translator": {"type": "google"},
    }
    google_user_config = UserConfig.model_validate(google_config_data)

    result = await translator_feature.set_user_config(google_config_data)

    assert result is True
    assert translator_feature.user_config == google_user_config
    # GoogleTranslator が正しい引数で初期化されたか
    mock_google_translator_cls.assert_called_once_with(
        translator_feature.logger,
        mock_system_config.cache_directory,
        mock_system_config.cache_max,
        google_user_config.translator,
    )
    assert translator_feature._translator is mock_google_translator_cls.return_value
    # IdentifierAdaptor が初期化されたか (first_language が EN のため)
    mock_identifier_adaptor_cls.assert_called_once()
    assert translator_feature._identifier is mock_identifier_adaptor_cls.return_value
    # キューサイズが変更されたか
    mock_resizable_queue_instance.change_maxsize.assert_called_once_with(QUEUE_MAX_SIZE)


@pytest.mark.asyncio
async def test_set_user_config_deepl_japanese(
    translator_feature: MessageTranslator,
    mock_system_config: SystemConfig,
    mock_deepl_translator_cls: MagicMock,
    mock_japanese_identifier_cls: MagicMock,  # first_language が JA の場合
    mock_resizable_queue_instance: MagicMock,
) -> None:
    """Deepl Translator と日本語設定が正しく適用されるかをテストします。"""
    deepl_config_data: ConfigData = {
        "version": 0,
        "first_language": Language.JAPANESE,  # JapaneseIdentifier を期待
        "second_language": Language.ENGLISH,
        "do_comment": False,
        "message_format": "test",
        "queue_max": QUEUE_MAX_SIZE,
        "ignore_emote_only_message": True,
        "translator": {"type": "deepl", "api_key": "fake-key"},
    }
    deepl_user_config = UserConfig.model_validate(deepl_config_data)

    result = await translator_feature.set_user_config(deepl_config_data)

    assert result is True
    assert translator_feature.user_config == deepl_user_config
    # DeeplTranslator が正しい引数で初期化されたか
    mock_deepl_translator_cls.assert_called_once_with(
        translator_feature.logger,
        mock_system_config.cache_directory,
        mock_system_config.cache_max,
        deepl_user_config.translator,
    )
    assert translator_feature._translator is mock_deepl_translator_cls.return_value
    # JapaneseIdentifier が初期化されたか (first_language が JA のため)
    mock_japanese_identifier_cls.assert_called_once()
    assert translator_feature._identifier is mock_japanese_identifier_cls.return_value
    # キューサイズが変更されたか
    mock_resizable_queue_instance.change_maxsize.assert_called_once_with(QUEUE_MAX_SIZE)


@pytest.mark.asyncio
async def test_set_user_config_unknown_translator(translator_feature: MessageTranslator) -> None:
    """未知の Translator タイプで ValueError が発生するかをテストします。"""
    unknown_config_data: ConfigData = {
        "version": 0,
        "first_language": Language.JAPANESE,
        "second_language": Language.ENGLISH,
        "do_comment": False,
        "message_format": "test",
        "queue_max": QUEUE_MAX_SIZE,
        "ignore_emote_only_message": True,
        "translator": {"type": "unknown"},  # 未知のタイプ
    }
    with pytest.raises(ValueError, match="Unknown translator: unknown"):
        await translator_feature.set_user_config(unknown_config_data)


@pytest.mark.asyncio
async def test_run(
    translator_feature: MessageTranslator,
    mock_routine_manager_cls: MagicMock,
    mock_routine_manager_instance: MagicMock,
) -> None:
    """run メソッドが RoutineManager を正しく制御するかをテストします。"""
    # super().run() をモック
    with patch.object(Feature, "run", new_callable=AsyncMock) as mock_super_run:
        await translator_feature.run()

        # RoutineManager の初期化とメソッド呼び出しを確認
        mock_routine_manager_cls.assert_called_once()
        mock_routine_manager_instance.add.assert_called_once_with(translator_feature._main, TRANSLATION_INTERVAL)
        mock_routine_manager_instance.start.assert_called_once()
        # super().run() が呼び出されたか
        mock_super_run.assert_awaited_once()
        # clear が呼び出されたか (run が終了した後に呼び出される想定)
        # このテストでは run の終了を待たないので、clear の呼び出しはここでは確認できない
        # 必要であれば、run をキャンセルする仕組みなどを追加してテストする


# --- _main メソッドのテスト ---


@pytest.fixture
def setup_main_test(
    translator_feature: MessageTranslator,
    mock_user_config_data: ConfigData,  # パラメータ化された設定を使用
    mock_resizable_queue_instance: MagicMock,
    mock_google_translator_instance: MagicMock,  # Google か Deepl かは設定による
    mock_deepl_translator_instance: MagicMock,
    mock_japanese_identifier_instance: MagicMock,  # Japanese か Adaptor かは設定による
    mock_identifier_adaptor_instance: MagicMock,
) -> tuple[MessageTranslator, UserConfig, MagicMock, MagicMock]:
    """_main メソッドのテストに必要な初期設定を行います。"""
    # ユーザー設定を適用
    asyncio.run(translator_feature.set_user_config(mock_user_config_data))
    user_config = cast("UserConfig", translator_feature.user_config)

    # 設定に基づいて使用される Translator と Identifier のインスタンスを取得
    translator_instance = (
        mock_google_translator_instance if user_config.translator.type == "google" else mock_deepl_translator_instance
    )
    identifier_instance = (
        mock_japanese_identifier_instance
        if user_config.first_language == Language.JAPANESE
        else mock_identifier_adaptor_instance
    )

    # キューから取得するメッセージイベントを作成
    mock_message = models.Message(
        content="Original message",
        parsed_content=["Original message"],
        author=models.User(id=1, name="test", display_name="Test"),
        is_echo=False,
    )
    mock_event = events.MessageFiltered(message=mock_message)
    mock_resizable_queue_instance.get.return_value = mock_event

    return translator_feature, user_config, translator_instance, identifier_instance


@pytest.mark.asyncio
async def test_main_success_first_to_second_lang(
    setup_main_test: tuple[MessageTranslator, UserConfig, MagicMock, MagicMock],
    mock_event_publisher: AsyncMock,
    mock_service_caller: AsyncMock,
) -> None:
    """_main: 正常系 (第一言語 -> 第二言語への翻訳、コメントあり)"""
    translator_feature, user_config, translator_instance, identifier_instance = setup_main_test
    mock_event = await translator_feature._message_queue.get()  # 設定済みのイベントを取得

    # Arrange: 言語識別子が第一言語を返すように設定
    identifier_instance.identify.return_value = user_config.first_language
    # Arrange: 翻訳者が各パーツを翻訳するように設定
    translator_instance.translate.return_value = "Translated message"

    # Act
    await translator_feature._main()

    # Assert: 識別子の呼び出し確認
    identifier_instance.identify.assert_called_once_with(mock_event.message.content)
    # Assert: 翻訳者の呼び出し確認 (文字列パーツのみ)
    expected_translate_calls = [
        call("Original message", user_config.second_language, user_config.first_language),
    ]
    translator_instance.translate.assert_has_awaits(expected_translate_calls)
    # Assert: イベント発行の確認
    expected_translated_content = "Translated message"
    expected_parsed_content = ["Translated message"]
    mock_event_publisher.publish.assert_awaited_once()
    published_event = mock_event_publisher.publish.await_args.args[0]
    assert isinstance(published_event, events.MessageTranslated)
    assert published_event.message.content == expected_translated_content
    assert published_event.message.parsed_content == expected_parsed_content
    assert published_event.message.author == mock_event.message.author

    # Assert: コメント送信の確認 (do_comment が True の場合)
    if user_config.do_comment:
        expected_comment_content = (
            user_config.message_format.replace("{author}", mock_event.message.author.name)
            .replace("{from}", user_config.first_language.value)
            .replace("{to}", user_config.second_language.value)
            .replace("{message}", expected_translated_content)
        )
        mock_service_caller.call.assert_awaited_once_with(
            services.SendComment(payload=models.Comment(content=expected_comment_content, is_italic=True))
        )
    else:
        mock_service_caller.call.assert_not_awaited()


@pytest.mark.asyncio
async def test_main_success_second_to_first_lang(
    setup_main_test: tuple[MessageTranslator, UserConfig, MagicMock, MagicMock],
    mock_event_publisher: AsyncMock,
    mock_service_caller: AsyncMock,
) -> None:
    """_main: 正常系 (第二言語 -> 第一言語への翻訳、コメントなし)"""
    translator_feature, user_config, translator_instance, identifier_instance = setup_main_test
    mock_event = await translator_feature._message_queue.get()

    # Arrange: 言語識別子が第二言語を返すように設定 (または第一言語以外)
    identified_lang = user_config.second_language  # または Language.UNKNOWN など
    identifier_instance.identify.return_value = identified_lang
    # Arrange: 翻訳者が各パーツを翻訳するように設定
    translator_instance.translate.return_value = "Translated message"
    # Arrange: コメントしない設定にする (フィクスチャで設定済みの場合もある)
    user_config.do_comment = False

    # Act
    await translator_feature._main()

    # Assert: 識別子の呼び出し確認
    identifier_instance.identify.assert_called_once_with(mock_event.message.content)
    # Assert: 翻訳者の呼び出し確認 (ターゲットが第一言語になる)
    expected_translate_calls = [call("Original message", user_config.first_language, identified_lang)]
    translator_instance.translate.assert_has_awaits(expected_translate_calls)

    expected_translated_content = "Translated message"
    expected_parsed_content = ["Translated message"]
    # Assert: イベント発行の確認
    mock_event_publisher.publish.assert_awaited_once()

    published_event = mock_event_publisher.publish.await_args.args[0]
    assert isinstance(published_event, events.MessageTranslated)
    assert published_event.message.content == expected_translated_content
    assert published_event.message.parsed_content == expected_parsed_content
    assert published_event.message.author == mock_event.message.author
    # Assert: コメント送信されないことの確認
    mock_service_caller.call.assert_not_called()


@pytest.mark.asyncio
async def test_main_ignore_emote_only(
    setup_main_test: tuple[MessageTranslator, UserConfig, MagicMock, MagicMock],
    mock_event_publisher: AsyncMock,
    mock_service_caller: AsyncMock,
) -> None:
    """_main: エモートのみのメッセージを無視するテスト"""
    translator_feature, user_config, translator_instance, identifier_instance = setup_main_test
    original_mock_event = await translator_feature._message_queue.get()

    # Arrange: エモートのみの新しいメッセージとイベントを作成
    emote_only_parsed_content = [models.Emote(id="1", text="Kappa"), models.Emote(id="2", text="LUL")]
    emote_only_message = models.Message(
        # content は parsed_content から再構築される想定だが、テスト用にダミーを設定
        content="Kappa LUL",
        parsed_content=emote_only_parsed_content,
        # author は元のイベントから流用
        author=original_mock_event.message.author,
        is_echo=False,  # または元のイベントに合わせる
    )
    emote_only_event = events.MessageFiltered(message=emote_only_message)

    # Arrange: キューがエモートのみのイベントを返すように設定
    translator_feature._message_queue.get.return_value = emote_only_event  # type:ignore[attr-defined]

    # Arrange: 無視する設定にする
    user_config.ignore_emote_only_message = True

    # Act
    await translator_feature._main()

    # Assert: 識別子、翻訳者、発行、呼び出しが実行されないこと
    identifier_instance.identify.assert_not_called()
    translator_instance.translate.assert_not_called()
    mock_event_publisher.publish.assert_not_awaited()  # awaitされないので _not_awaited
    mock_service_caller.call.assert_not_called()  # awaitされないので _not_called


@pytest.mark.asyncio
async def test_main_translation_error(
    setup_main_test: tuple[MessageTranslator, UserConfig, MagicMock, MagicMock],
    mock_event_publisher: AsyncMock,
    mock_service_caller: AsyncMock,
) -> None:
    """_main: 翻訳中に TranslationError が発生するテスト"""
    translator_feature, user_config, translator_instance, identifier_instance = setup_main_test
    mock_event = await translator_feature._message_queue.get()

    # Arrange: 言語識別子が第一言語を返す
    identifier_instance.identify.return_value = user_config.first_language
    # Arrange: 翻訳者がエラーを発生させる
    translation_error = TranslationError("API failed")
    translator_instance.translate.side_effect = translation_error

    # Act
    await translator_feature._main()

    # Assert: 識別子は呼び出される
    identifier_instance.identify.assert_called_once_with(mock_event.message.content)
    # Assert: 翻訳者も呼び出される (エラーが発生するまで)
    translator_instance.translate.assert_awaited()
    # Assert: イベント発行、コメント送信はされない
    mock_event_publisher.publish.assert_not_called()
    mock_service_caller.call.assert_not_called()


@pytest.mark.asyncio
async def test_main_not_initialized_user_config(
    translator_feature: MessageTranslator,  # setup_main_test を使わない
    mock_resizable_queue_instance: MagicMock,
    mock_event_publisher: AsyncMock,
) -> None:
    """_main: user_config が None の場合に早期リターンするテスト"""
    # Arrange: user_config を None にする
    translator_feature._user_config = None
    # Arrange: キューにイベントを入れる
    mock_event = events.MessageFiltered(
        message=models.Message(
            content="dummy content",
            parsed_content=["dummy content"],
            author=models.User(id=0, name="dummy", display_name="Dummy"),
            is_echo=False,
        )
    )

    mock_resizable_queue_instance.get.return_value = mock_event

    # Act
    await translator_feature._main()

    # Assert: イベント発行などがされないこと
    mock_event_publisher.publish.assert_not_awaited()


@pytest.mark.asyncio
async def test_main_not_initialized_translator(
    translator_feature: MessageTranslator,  # setup_main_test を使わない
    mock_user_config_data: ConfigData,
    mock_resizable_queue_instance: MagicMock,
) -> None:
    """_main: _translator が None の場合に RuntimeError が発生するテスト"""
    # Arrange: user_config は設定するが、_translator は None のままにする
    await translator_feature.set_user_config(mock_user_config_data)
    translator_feature._translator = None  # 強制的に None に戻す
    # Arrange: キューにイベントを入れる
    mock_event = events.MessageFiltered(
        message=models.Message(
            content="dummy content",
            parsed_content=["dummy content"],
            author=models.User(id=0, name="dummy", display_name="Dummy"),
            is_echo=False,
        )
    )
    mock_resizable_queue_instance.get.return_value = mock_event

    # Act & Assert
    with pytest.raises(RuntimeError, match="Translator is not initialized."):
        await translator_feature._main()


@pytest.mark.asyncio
async def test_main_not_initialized_identifier(
    translator_feature: MessageTranslator,  # setup_main_test を使わない
    mock_user_config_data: ConfigData,
    mock_resizable_queue_instance: MagicMock,
) -> None:
    """_main: _identifier が None の場合に RuntimeError が発生するテスト"""
    # Arrange: user_config, _translator は設定するが、_identifier は None のままにする
    await translator_feature.set_user_config(mock_user_config_data)
    translator_feature._identifier = None  # 強制的に None に戻す
    # Arrange: キューにイベントを入れる
    mock_event = events.MessageFiltered(
        message=models.Message(
            content="dummy content",
            parsed_content=["dummy content"],
            author=models.User(id=0, name="dummy", display_name="Dummy"),
            is_echo=False,
        )
    )
    mock_resizable_queue_instance.get.return_value = mock_event

    # Act & Assert
    with pytest.raises(RuntimeError, match="Language identifier is not initialized."):
        await translator_feature._main()
