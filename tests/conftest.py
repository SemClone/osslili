"""Pytest configuration file."""

import pytest
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def sample_data():
    """Provide sample data for tests."""
    return {
        "test": "data",
        "sample": "value"
    }
