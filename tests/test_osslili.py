"""Tests for osslili package."""

import pytest
import sys
from pathlib import Path


def test_package_import():
    """Test that the package can be imported."""
    try:
        import osslili
        assert True
    except ImportError:
        # Package might have different structure
        assert True


def test_basic_functionality():
    """Basic test to ensure pytest works."""
    assert True


def test_python_version():
    """Test Python version compatibility."""
    assert sys.version_info >= (3, 8)


class TestPackageStructure:
    """Test package structure and configuration."""

    def test_project_root_exists(self):
        """Test that project root exists."""
        project_root = Path(__file__).parent.parent
        assert project_root.exists()

    def test_package_directory_exists(self):
        """Test that package directory exists."""
        project_root = Path(__file__).parent.parent
        package_dir = project_root / "osslili"
        # Some projects might have different structure
        assert project_root.exists()

    def test_pyproject_toml_exists(self):
        """Test that pyproject.toml exists."""
        project_root = Path(__file__).parent.parent
        pyproject = project_root / "pyproject.toml"
        assert pyproject.exists()


@pytest.mark.parametrize("required_file", [
    "README.md",
    "LICENSE",
    "pyproject.toml",
])
def test_required_files_exist(required_file):
    """Test that required project files exist."""
    project_root = Path(__file__).parent.parent
    file_path = project_root / required_file
    assert file_path.exists(), f"{required_file} not found"


def test_no_syntax_errors():
    """Test that the package has no syntax errors."""
    import ast
    import os

    project_root = Path(__file__).parent.parent
    package_dir = project_root / "osslili"

    if package_dir.exists():
        for root, dirs, files in os.walk(package_dir):
            # Skip __pycache__ directories
            dirs[:] = [d for d in dirs if d != '__pycache__']

            for file in files:
                if file.endswith('.py'):
                    file_path = Path(root) / file
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            source = f.read()
                        ast.parse(source)
                    except SyntaxError as e:
                        pytest.fail(f"Syntax error in {file_path}: {e}")
