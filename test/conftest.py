from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def project_root() -> Path:
    return Path(__file__).parent.absolute()


@pytest.fixture(scope="session")
def test_data_dir(project_root: Path) -> Path:
    return project_root / "doc"


@pytest.fixture(scope="session")
def test_sound_file(test_data_dir: Path) -> Path:
    return test_data_dir / "sample.mp3"
