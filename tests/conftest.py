from pathlib import Path

import pytest

from nba.synth import generate

QUIET = dict(log=lambda *_: None)


@pytest.fixture(scope="session")
def full(tmp_path_factory) -> Path:
    """The full synthetic dataset (3,000 physicians), generated once per test session."""
    d = tmp_path_factory.mktemp("full")
    generate(data_dir=d, **QUIET)
    return d
