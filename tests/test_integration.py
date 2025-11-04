"""Integration tests for osslili."""

import pytest
from pathlib import Path


def test_project_imports():
    """Test that project modules can be imported."""
    # This will be customized per project
    assert True


def test_documentation_exists():
    """Test that documentation files exist."""
    project_root = Path(__file__).parent.parent

    docs = [
        "README.md",
        "CONTRIBUTING.md",
        "AUTHORS.md",
    ]

    for doc in docs:
        doc_path = project_root / doc
        assert doc_path.exists(), f"Documentation {doc} is missing"


def test_workflow_files_exist():
    """Test that GitHub workflow files exist."""
    project_root = Path(__file__).parent.parent
    workflows_dir = project_root / ".github" / "workflows"

    if workflows_dir.exists():
        workflow_files = list(workflows_dir.glob("*.yml"))
        assert len(workflow_files) > 0, "No workflow files found"
