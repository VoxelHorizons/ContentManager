import json

import yaml

from content_manager.cli import main
from content_manager.core import Workspace, _palette, SUPPORTED_TARGETS
from content_manager.lint import lint_workspace
from test_content_manager import fixture_pack


def test_lint_clean_workspace_is_read_only(tmp_path):
    pack, _ = fixture_pack(tmp_path)
    before = {p.relative_to(pack): p.read_bytes() for p in pack.rglob('*') if p.is_file()}
    report = lint_workspace(Workspace(pack))
    assert report.count("error") == 0
    assert report.count("warning") == 0
    assert report.as_dict()["authoritative"] is False
    after = {p.relative_to(pack): p.read_bytes() for p in pack.rglob('*') if p.is_file()}
    assert before == after


def test_lint_json_reports_missing_texture_and_exit_code(tmp_path, capsys):
    pack, _ = fixture_pack(tmp_path)
    model = pack / "assets/voxel/models/furniture/oak_table.json"
    data = json.loads(model.read_text())
    data["textures"]["wood"] = "voxel:missing"
    model.write_text(json.dumps(data))
    assert main(["lint", str(pack), "--json"]) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["schema_version"] == 1
    assert result["summary"]["errors"] >= 1
    assert any(f["code"] == "missing-texture" for f in result["findings"])


def test_lint_external_vanilla_parent_is_information_not_failure(tmp_path, capsys):
    pack, _ = fixture_pack(tmp_path)
    model = pack / "assets/voxel/models/furniture/oak_table.json"
    model.write_text(json.dumps({
        "parent": "minecraft:item/generated",
        "textures": {"layer0": "minecraft:item/paper"},
    }))
    assert main(["lint", str(pack), "--json"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["summary"]["errors"] == 0
    assert any(f["code"] == "external-vanilla-parent" and f["severity"] == "info"
               for f in result["findings"])


def test_lint_missing_workspace_dependency_is_warning_only(tmp_path, capsys):
    pack, _ = fixture_pack(tmp_path)
    (pack / "pack.yml").write_text("schema: 1\nnamespace: voxel\ndependencies: [externalpack]\n")
    assert main(["lint", str(pack), "--json"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["summary"]["warnings"] == 1
    assert main(["lint", str(pack), "--strict"]) == 1


def test_lint_json_survives_workspace_parse_error(tmp_path, capsys):
    assert main(["lint", str(tmp_path), "--json"]) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["summary"]["errors"] == 1
    assert result["findings"][0]["code"] == "workspace-invalid"
    assert result["authoritative"] is False


def test_lint_warns_when_item_has_both_addon_sections(tmp_path):
    pack, _ = fixture_pack(tmp_path)
    path = pack / "content/items.yml"
    data = yaml.safe_load(path.read_text())
    data["items"]["oak_table"]["properties"]["vehicle"] = {"type": "LAND"}
    path.write_text(yaml.safe_dump(data))
    report = lint_workspace(Workspace(pack))
    assert any(f.code == "multiple-addon-properties" for f in report.findings)


def test_mc_26_3_target_is_curated_not_a_compiler_claim():
    assert "mc-26.2" in SUPPORTED_TARGETS
    assert "mc-26.3" in SUPPORTED_TARGETS
    assert _palette("wood", "mc-26.3") == _palette("wood", "mc-26.2")
    assert len(_palette("wool", "mc-26.3")) == 16
