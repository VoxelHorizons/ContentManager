import json
from pathlib import Path
import pytest
from content_manager.core import Workspace, ContentError, plan_family, apply_plan, rollback_snapshot


def fixture_pack(tmp_path, *, kind="furniture", with_model=True):
    pack = tmp_path / "content" / "voxel"
    (pack / "content").mkdir(parents=True)
    (pack / "pack.yml").write_text("schema: 1\nnamespace: voxel\n", encoding="utf-8")
    source = "oak_table" if kind == "furniture" else "white_wool_chair"
    texture = "minecraft:block/oak_planks" if kind == "furniture" else "minecraft:block/white_wool"
    slot = "wood" if kind == "furniture" else "wool"
    entry = {"items": {source: {
        "material": "minecraft:paper", "display_name": source,
        "render": {"model": f"voxel:furniture/{source}"},
        "properties": {kind: {"rotation_step": 90} if kind == "furniture" else {"type": "LAND"}},
    }}}
    import yaml
    (pack / "content" / "items.yml").write_text(yaml.safe_dump(entry), encoding="utf-8")
    model = pack / "assets" / "voxel" / "models" / "furniture" / f"{source}.json"
    if with_model:
        model.parent.mkdir(parents=True)
        model.write_text(json.dumps({"textures": {slot: texture, "particle": f"#{slot}"},
                                     "elements": [{"from": [0,0,0], "to": [16,16,16],
                                                   "faces": {"up": {"texture": f"#{slot}"}}}]}), encoding="utf-8")
    return pack, f"voxel:{source}"


def test_scan_and_resolve(tmp_path):
    pack, source = fixture_pack(tmp_path)
    ws = Workspace(pack.parent)
    assert ws.kind(source) == "Furniture"
    assert ws.resolve_item(source)["properties"]["furniture"]["rotation_step"] == 90
    assert ws.model_file(source).is_file()
    assert not (pack / ".contentmanager").exists()


def test_alias_generated_and_repeat_idempotent(tmp_path):
    pack, source = fixture_pack(tmp_path)
    ws = Workspace(pack.parent)
    plan = plan_family(ws, source, "wood", selected=("oak", "spruce", "birch"))
    assert len(plan.changed) == 5  # two children * yaml + model, plus manifest
    assert not (pack / ".contentmanager").exists()
    snapshot = apply_plan(plan)
    assert snapshot.is_dir()
    refresh = Workspace(pack.parent)
    assert "voxel:spruce_table" in refresh.items
    child = refresh.resolve_item("voxel:spruce_table")
    assert child["properties"]["furniture"]["rotation_step"] == 90
    model_file = refresh.model_file("voxel:spruce_table")
    assert json.loads(model_file.read_text())["textures"]["wood"] == "minecraft:block/spruce_planks"
    second = plan_family(refresh, source, "wood", selected=("oak", "spruce", "birch"))
    assert not second.changed


def test_clone_wool_colors(tmp_path):
    pack, source = fixture_pack(tmp_path, kind="furniture")
    # Replace source with wool names + texture reference
    source_yaml = pack / "content" / "items.yml"
    source_yaml.write_text(source_yaml.read_text().replace("oak_table", "white_wool_chair"), encoding="utf-8")
    model_old = pack / "assets" / "voxel" / "models" / "furniture" / "oak_table.json"
    model_new = model_old.with_name("white_wool_chair.json")
    model_new.write_text(model_old.read_text().replace("oak_planks", "white_wool").replace("\"wood\"", "\"wool\"").replace("#wood", "#wool"), encoding="utf-8")
    model_old.unlink()
    ws = Workspace(pack.parent)
    plan = plan_family(ws, "voxel:white_wool_chair", "wool", strategy="clone", selected=("white", "light_blue", "red"))
    apply_plan(plan)
    resolved = Workspace(pack.parent).resolve_item("voxel:light_blue_wool_chair")
    assert "Light Blue Wool Chair" in resolved["display_name"]
    output = pack / "assets" / "voxel" / "models" / "furniture" / "light_blue_wool_chair.json"
    assert json.loads(output.read_text())["textures"]["wool"] == "minecraft:block/light_blue_wool"


def test_modified_generated_file_is_never_overwritten(tmp_path):
    pack, source = fixture_pack(tmp_path)
    plan = plan_family(Workspace(pack.parent), source, "wood", selected=("oak", "birch"))
    apply_plan(plan)
    changed_model = pack / "assets" / "voxel" / "models" / "furniture" / "birch_table.json"
    changed_model.write_text("{\"manual\": true}", encoding="utf-8")
    with pytest.raises(ContentError, match="Refusing to overwrite"):
        plan_family(Workspace(pack.parent), source, "wood", selected=("oak", "birch"))


def test_refuse_collision_with_existing_id(tmp_path):
    pack, source = fixture_pack(tmp_path)
    (pack / "content" / "other.yml").write_text("items:\n  spruce_table:\n    material: paper\n", encoding="utf-8")
    with pytest.raises(ContentError, match="already belongs"):
        plan_family(Workspace(pack.parent), source, "wood", selected=("oak", "spruce"))


def test_stale_plan_detected_before_apply(tmp_path):
    pack, source = fixture_pack(tmp_path)
    plan = plan_family(Workspace(pack.parent), source, "wood", selected=("oak", "spruce"))
    with (pack / "content" / "items.yml").open("a") as stream:
        stream.write("# external change\n")
    with pytest.raises(ContentError, match="Source item or model changed"):
        apply_plan(plan)


def test_snapshot_restore(tmp_path):
    pack, source = fixture_pack(tmp_path)
    plan = plan_family(Workspace(pack.parent), source, "wood", selected=("oak", "spruce"))
    snapshot = apply_plan(plan)
    assert len(Workspace(pack.parent).items) == 2
    rollback_snapshot(pack, snapshot)
    assert len(Workspace(pack.parent).items) == 1
    assert not (pack / "assets" / "voxel" / "models" / "furniture" / "spruce_table.json").exists()


def test_snapshot_restore_rejects_external_edit(tmp_path):
    pack, source = fixture_pack(tmp_path)
    snapshot = apply_plan(plan_family(Workspace(pack.parent), source, "wood", selected=("oak", "spruce")))
    generated = pack / "content" / "generated" / "contentmanager" / "oak_table__wood" / "spruce_table.yml"
    generated.write_text(generated.read_text() + "# edited\n")
    with pytest.raises(ContentError, match="changed since apply"):
        rollback_snapshot(pack, snapshot)


def test_invalid_generated_slot_fails_preflight(tmp_path):
    pack, source = fixture_pack(tmp_path)
    with pytest.raises(ContentError, match="Texture slot"):
        plan_family(Workspace(pack.parent), source, "wood", texture_slot="all", selected=("oak", "birch"))


def test_pack_13_limited_woods(tmp_path):
    pack, source = fixture_pack(tmp_path)
    with pytest.raises(ContentError, match="Selected materials"):
        plan_family(Workspace(pack.parent), source, "wood", target="mc-1.13.2", selected=("oak", "mangrove"))


def test_duplicate_yaml_rejected(tmp_path):
    pack, source = fixture_pack(tmp_path)
    (pack / "content" / "items.yml").write_text("items:\n  oak_table: {}\n  oak_table: {}\n", encoding="utf-8")
    with pytest.raises(ContentError, match="Duplicate YAML key"):
        Workspace(pack.parent)


def test_parent_inherited_render(tmp_path):
    pack, source = fixture_pack(tmp_path)
    yml = pack / "content" / "items.yml"
    yml.write_text("items:\n  table_base:\n    abstract: true\n    material: paper\n    render:\n      model: voxel:furniture/oak_table\n  oak_table:\n    extends: table_base\n    abstract: false\n    properties:\n      furniture:\n        rotation_step: 90\n", encoding="utf-8")
    ws = Workspace(pack.parent)
    plan = plan_family(ws, source, "wood", selected=("oak", "spruce"))
    snapshot = apply_plan(plan)
    assert snapshot.exists()


def test_unknown_pack_root_rejected(tmp_path):
    (tmp_path / "misc").mkdir()
    with pytest.raises(ContentError, match="Select|No content"):
        Workspace(tmp_path)


def test_create_new_furniture_from_existing_model(tmp_path):
    from content_manager.core import plan_new_item
    pack, _ = fixture_pack(tmp_path)
    ws = Workspace(pack.parent)
    plan = plan_new_item(ws, "voxel", "spruce_showcase", "&fSpruce Showcase",
                         "voxel:furniture/oak_table", "furniture")
    assert len(plan.changed) == 1
    apply_plan(plan)
    refreshed = Workspace(pack.parent)
    assert refreshed.kind("voxel:spruce_showcase") == "Furniture"
    assert refreshed.resolve_item("voxel:spruce_showcase")["render"]["model"] == "voxel:furniture/oak_table"


def test_new_item_requires_existing_asset(tmp_path):
    from content_manager.core import plan_new_item
    pack, _ = fixture_pack(tmp_path)
    with pytest.raises(ContentError, match="not found"):
        plan_new_item(Workspace(pack.parent), "voxel", "missing", "Missing", "voxel:furniture/absent")
