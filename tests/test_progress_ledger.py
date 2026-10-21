from scripts.check_progress import needs_checkpoint


def test_code_and_workflow_changes_require_checkpoint():
    assert needs_checkpoint({"content_manager/assets.py"})
    assert needs_checkpoint({"tests/test_assets.py"})
    assert needs_checkpoint({"scripts/check_progress.py"})
    assert needs_checkpoint({".github/workflows/python-ci.yml"})
    assert needs_checkpoint({"pyproject.toml"})


def test_docs_and_packaging_artifacts_do_not_trigger_guard():
    assert not needs_checkpoint({"docs/ROADMAP.md", "docs/DEVELOPMENT-LOG.md"})
    assert not needs_checkpoint({"README.md", ".gitignore"})
