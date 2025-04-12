import json
import logging
from pathlib import Path
from unittest.mock import MagicMock, call

import pytest
from pydantic import BaseModel

from utils.model_file import ModelFile


class Model(BaseModel):
    name: str
    value: int


@pytest.fixture
def mock_logger() -> MagicMock:
    logger = MagicMock(spec=logging.Logger)
    logger.getChild.return_value = logger
    return logger


@pytest.fixture
def mock_file(tmp_path: Path) -> Path:
    return tmp_path / "test_file.json"


def test_model_file_init_new_file(mock_logger: MagicMock, mock_file: Path) -> None:
    model_file = ModelFile(Model, mock_file, mock_logger)
    assert model_file.data is None
    mock_logger.debug.assert_called_with("Data file did not found: %s", mock_file)


def test_model_file_init_existing_file(mock_logger: MagicMock, mock_file: Path) -> None:
    data = {"name": "test", "value": 1}
    with mock_file.open("w", encoding="utf-8") as f:
        json.dump(data, f)

    model_file = ModelFile(Model, mock_file, mock_logger)
    assert model_file.data == Model(**data)
    mock_logger.debug.assert_called_with("Loaded data: %s", Model(**data))


def test_model_file_init_invalid_json(mock_logger: MagicMock, mock_file: Path) -> None:
    with mock_file.open("w", encoding="utf-8") as f:
        f.write("invalid json")

    model_file = ModelFile(Model, mock_file, mock_logger)
    assert model_file.data is None
    mock_logger.exception.assert_called_once()


def test_model_file_init_invalid_model(mock_logger: MagicMock, mock_file: Path) -> None:
    data = {"name": "test", "value": "invalid"}
    with mock_file.open("w", encoding="utf-8") as f:
        json.dump(data, f)

    model_file = ModelFile(Model, mock_file, mock_logger)
    assert model_file.data is None
    mock_logger.exception.assert_called_once()


def test_model_file_update(mock_logger: MagicMock, mock_file: Path) -> None:
    model_file = ModelFile(Model, mock_file, mock_logger)
    new_data = Model(name="new", value=2)
    model_file.update(new_data)
    assert model_file.data == new_data
    assert mock_file.exists()

    with mock_file.open("r", encoding="utf-8") as f:
        loaded_data = json.load(f)
        assert loaded_data == {"name": "new", "value": 2}
    mock_logger.debug.assert_called_with("Saving data to %s", mock_file)


def test_model_file_update_same_data(mock_logger: MagicMock, mock_file: Path) -> None:
    data = {"name": "test", "value": 1}
    model_file = ModelFile(Model, mock_file, mock_logger)
    model_file.update(Model(**data))
    model_file.update(Model(**data))
    mock_logger.debug.assert_has_calls(
        [call("Updating to %s : %s", Model(name="test", value=1), mock_file), call("Saving data to %s", mock_file)],
    )


def test_model_file_clear(mock_logger: MagicMock, mock_file: Path) -> None:
    data = {"name": "test", "value": 1}
    with mock_file.open("w", encoding="utf-8") as f:
        json.dump(data, f)

    model_file = ModelFile(Model, mock_file, mock_logger)
    model_file.clear()
    assert model_file.data is None
    assert not mock_file.exists()
    mock_logger.debug.assert_called_with("Clearing data from %s", mock_file)


def test_model_file_clear_not_exist(mock_logger: MagicMock, mock_file: Path) -> None:
    model_file = ModelFile(Model, mock_file, mock_logger)
    model_file.clear()
    assert model_file.data is None
    assert not mock_file.exists()
    mock_logger.debug.assert_called_with("Clearing data from %s", mock_file)
