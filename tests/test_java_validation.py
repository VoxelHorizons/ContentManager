import json
from pathlib import Path
import shutil
import subprocess

import pytest

from content_manager.core import ContentError, Workspace
from content_manager.cli import main
from content_manager.validation import _classpath, validate_java

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _setup(tmp_path, name="java_valid"):
    root = tmp_path / "content"
    shutil.copytree(FIXTURES / name, root)
    jar = tmp_path / "compiler.jar"
    jar.write_bytes(b"dummy jar for invocation tests")
    cp = tmp_path / "classpath.txt"
    cp.write_text(str(jar), encoding="utf-8")
    return root, cp


def _complete(args, **kwargs):
    assert isinstance(args, list)
    assert args[0] == "java"
    assert args[1] == "--class-path"
    assert "VoxelCoreValidationBridge.java" in args[3]
    stage = Path(args[4])
    assert (stage / "voxel/content/items.yml").exists()
    assert args[-1] == "mc-26.3"
    Path(kwargs["stdout"].name).write_text(
        "VOXELCORE_VALIDATION_OK\tmc-26.3\t1\t0\t1\n", encoding="utf-8"
    )
    return subprocess.CompletedProcess(args, 0)


def test_java_source_bridge_stages_copied_workspace(tmp_path, monkeypatch):
    root, cp = _setup(tmp_path)
    original = (root / "voxel/content/items.yml").read_bytes()
    (root / "voxel/.contentmanager").mkdir()
    (root / "voxel/.contentmanager/private.json").write_text("private")
    allocation = tmp_path / "alloc.yml"
    allocation.write_text("schema: 3\n", encoding="utf-8")

    def fake(args, **kwargs):
        stage = Path(args[4])
        assert not (stage / "voxel/.contentmanager").exists()
        assert Path(args[5]).read_text() == "schema: 3\n"
        (stage / "voxel/content/items.yml").write_text("this modification is sandboxed")
        return _complete_with_marker(args, kwargs)

    def _complete_with_marker(args, kwargs):
        Path(kwargs["stdout"].name).write_text(
            "VOXELCORE_VALIDATION_OK\tmc-26.3\t1\t0\t1\n", encoding="utf-8"
        )
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(subprocess, "run", fake)
    result = validate_java(Workspace(root), cp, allocations=allocation)
    assert result.success
    assert result.input_files == 3
    assert len(result.input_sha256) == 64
    assert result.rendered_items == 1
    assert not result.as_dict()["compiler_classpath_attested"]
    assert (root / "voxel/content/items.yml").read_bytes() == original
    assert allocation.read_text() == "schema: 3\n"


def test_java_validation_rejects_success_without_marker(tmp_path, monkeypatch):
    root, cp = _setup(tmp_path)

    def misleading(args, **kwargs):
        Path(kwargs["stdout"].name).write_text("nothing validated\n")
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(subprocess, "run", misleading)
    result = validate_java(Workspace(root), cp)
    assert not result.success
    assert "success marker" in result.stderr
    assert result.rendered_items is None


def test_java_validation_failed_compiler_and_cli_json(tmp_path, monkeypatch, capsys):
    root, cp = _setup(tmp_path)

    def failed(args, **kwargs):
        Path(kwargs["stderr"].name).write_text("VOXELCORE_VALIDATION_FAILED: invalid yaml\n")
        return subprocess.CompletedProcess(args, 1)

    monkeypatch.setattr(subprocess, "run", failed)
    assert main(["validate-java", str(root), "--classpath-file", str(cp), "--json"]) == 1
    data = json.loads(capsys.readouterr().out)
    assert not data["success"]
    assert data["process"]["exit_code"] == 1
    assert "invalid yaml" in data["process"]["stderr"]


def test_java_validation_timeout_and_bad_classpath(tmp_path, monkeypatch):
    root, cp = _setup(tmp_path)
    with pytest.raises(ContentError, match="Missing or invalid Java classpath"):
        cp.write_text("/definitely/missing/file.jar")
        validate_java(Workspace(root), cp)

    cp.write_text(str(tmp_path / "compiler.jar"))

    def timeout(args, **kwargs):
        raise subprocess.TimeoutExpired(args, kwargs["timeout"])

    monkeypatch.setattr(subprocess, "run", timeout)
    with pytest.raises(ContentError, match="exceeded"):
        validate_java(Workspace(root), cp, timeout_seconds=1)


def test_java_validation_rejects_symlinked_inputs(tmp_path):
    root, cp = _setup(tmp_path)
    item = root / "voxel/content/items.yml"
    replacement = tmp_path / "outside.yml"
    replacement.write_bytes(item.read_bytes())
    item.unlink()
    try:
        item.symlink_to(replacement)
    except OSError:
        pytest.skip("Symlinks unavailable")
    with pytest.raises(ContentError, match="Linked/special|Path escapes|Symlink"):
        validate_java(Workspace(root), cp)


def test_java_fixture_is_scannable_and_invalid_duplicate_rejected(tmp_path):
    good, _ = _setup(tmp_path)
    workspace = Workspace(good)
    assert "voxel:oak_table" in workspace.items
    with pytest.raises(ContentError, match="Duplicate YAML key"):
        Workspace(FIXTURES / "java_invalid_duplicate")


def test_validate_java_rejects_bad_timeout_before_running(tmp_path, monkeypatch):
    root, cp = _setup(tmp_path)
    def no_execution(*args, **kwargs):
        raise AssertionError("JVM must not be started")
    monkeypatch.setattr(subprocess, "run", no_execution)
    with pytest.raises(ContentError, match="timeout"):
        validate_java(Workspace(root), cp, timeout_seconds=0)


def test_java_validator_accepts_windows_crlf_success_marker(tmp_path, monkeypatch):
    root, cp = _setup(tmp_path)

    def fake(args, **kwargs):
        Path(kwargs["stdout"].name).write_bytes(
            b"VOXELCORE_VALIDATION_OK\tmc-26.3\t1\t0\t1\r\n"
        )
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(subprocess, "run", fake)
    result = validate_java(Workspace(root), cp)
    assert result.success and result.rendered_items == 1


def test_java_unique_invalid_fixture_gets_past_python_scan(tmp_path):
    workspace = Workspace(FIXTURES / "java_invalid_render")
    assert "voxel:invalid_render" in workspace.items
    assert "unsupported_java_parser_key" in (
        workspace.items["voxel:invalid_render"].definition["render"]
    )


def test_java_json_errors_are_structured(tmp_path, capsys):
    root, cp = _setup(tmp_path)
    cp.write_text("/missing/compiler.jar")
    assert main(["validate-java", str(root), "--classpath-file", str(cp), "--json"]) == 1
    data = json.loads(capsys.readouterr().out)
    assert data["success"] is False
    assert data["compiler_classpath_attested"] is False
    assert "Missing or invalid Java classpath" in data["error"]
