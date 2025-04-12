import json
import logging
from pathlib import Path

from pydantic import BaseModel


class ModelFileError(RuntimeError):
    pass


class ModelFile[T: BaseModel]:
    def __init__(self, model_type: type[T], file: Path, logger: logging.Logger) -> None:
        self.model_type = model_type
        self._file = file
        self._logger = logger.getChild(self.__class__.__name__)

        self._data = self._load()

    @property
    def data(self) -> T | None:
        return self._data

    def update(self, data: T) -> None:
        if self._data == data:
            return

        self._logger.debug("Updating to %s : %s", data, self._file)

        self._save(data)
        self._data = data

    def clear(self) -> None:
        self._logger.debug("Clearing data from %s", self._file)
        self._data = None
        if self._file.exists():
            self._file.unlink()

    def _save(self, data: T) -> None:
        self._logger.debug("Saving data to %s", self._file)

        try:
            with self._file.open("w", encoding="utf-8") as f:
                f.write(data.model_dump_json(indent=4))
        except (OSError, TypeError) as e:
            msg = f"Failed to save data to {self._file!s}"
            self._logger.exception(msg)
            raise ModelFileError(msg) from e

    def _load(self) -> T | None:
        self._logger.debug("Loading data from %s", self._file)
        if not self._file.exists():
            self._logger.debug("Data file did not found: %s", self._file)
            return None

        try:
            with self._file.open("r", encoding="utf-8") as f:
                data = json.load(f)
                model = self.model_type.model_validate(data)
                self._logger.debug("Loaded data: %s", model)
                return model
        except (OSError, json.JSONDecodeError, ValueError):
            msg = f"Failed to load data from {self._file}"
            self._logger.exception(msg)
            return None
