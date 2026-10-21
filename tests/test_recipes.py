import copy
import json
import pytest
from content_manager.core import Workspace, ContentError, apply_plan
from content_manager.assets import ModelResolver
from content_manager.recipes import plan_recipe
from test_content_manager import fixture_pack


def setup(tmp_path):
    pack, source = fixture_pack(tmp_path)
    model_file = pack / 'assets/voxel/models/furniture/oak_table.json'
    model = json.loads(model_file.read_text())
    model['textures']['cloth'] = 'minecraft:block/white_wool'
    model_file.write_text(json.dumps(model))
    recipe = {'recipe_schema': 1, 'id': 'upholstered', 'source': source,
        'axes': {'wood': {'oak': 'minecraft:block/oak_planks', 'spruce': 'minecraft:block/spruce_planks'},
                 'color': {'white': 'minecraft:block/white_wool', 'red': 'minecraft:block/red_wool'}},
        'texture_slots': {'wood': 'wood', 'cloth': 'color'},
        'items': {source: '{wood}_{color}_table'}}
    return pack, recipe


def test_cartesian_product_repeat_and_parent_updates(tmp_path):
    pack, recipe = setup(tmp_path)
    plan = plan_recipe(Workspace(pack), recipe)
    assert len(plan.changed) == 9
    apply_plan(plan)
    ws = Workspace(pack)
    for wood in ('oak', 'spruce'):
        for color in ('white', 'red'):
            ident = f'voxel:{wood}_{color}_table'
            result = ws.resolve_item(ident)
            assert result['properties']['furniture']['rotation_step'] == 90
            model = ModelResolver(ws).resolve(result['render']['model'])
            assert model.textures['wood'] == f'minecraft:block/{wood}_planks'
            assert model.textures['cloth'] == f'minecraft:block/{color}_wool'
    assert not plan_recipe(ws, recipe).changed
    manifest = json.loads(plan.manifest_path.read_text())
    assert manifest['recipe'] == recipe
    assert len(manifest['revision_sha256']) == 64


def test_recipe_duplicate_names_fail_before_write(tmp_path):
    pack, recipe = setup(tmp_path)
    recipe['items'][recipe['source']] = '{wood}_new_table'
    with pytest.raises(ContentError, match='duplicate ID'):
        plan_recipe(Workspace(pack), recipe)
    assert not (pack / '.contentmanager').exists()


def test_customization_conflict_preserves_human_edit(tmp_path):
    pack, recipe = setup(tmp_path)
    plan = plan_recipe(Workspace(pack), recipe)
    apply_plan(plan)
    output = plan.outputs[0].path
    output.write_bytes(output.read_bytes() + b'# manual customization\n')
    before = output.read_bytes()
    with pytest.raises(ContentError, match='manually changed'):
        plan_recipe(Workspace(pack), recipe)
    assert output.read_bytes() == before


def test_bound_axis_and_unknown_expression_rejected(tmp_path):
    pack, recipe = setup(tmp_path)
    recipe['items'][recipe['source']] = '{wood.__class__}_{color}'
    with pytest.raises(ContentError, match='plain'):
        plan_recipe(Workspace(pack), recipe)


def test_recipe_bound_before_cartesian_expansion(tmp_path):
    pack, recipe = setup(tmp_path)
    recipe['axes']['wood'] = {f'wood{i}': 'minecraft:block/oak_planks' for i in range(2000)}
    with pytest.raises(ContentError, match='4096'):
        plan_recipe(Workspace(pack), recipe)


def test_recipe_state_remap_and_abstract_preservation(tmp_path):
    from test_assets import linked_pack
    import yaml
    pack, source = linked_pack(tmp_path)
    for model in (pack / 'assets/voxel/models/furniture').glob('*.json'):
        data = json.loads(model.read_text())
        data['textures']['cloth'] = 'minecraft:block/white_wool'
        model.write_text(json.dumps(data))
    recipe = {'recipe_schema': 1, 'id': 'states', 'source': source,
        'axes': {'wood': {'birch': 'minecraft:block/birch_planks'}, 'color': {'red': 'minecraft:block/red_wool'}},
        'texture_slots': {'wood': 'wood', 'cloth': 'color'},
        'items': {source: '{wood}_{color}_table', 'voxel:oak_open': '{wood}_{color}_open'}}
    plan = plan_recipe(Workspace(pack), recipe)
    apply_plan(plan)
    ws = Workspace(pack)
    assert ws.resolve_item('voxel:birch_red_open')['abstract'] is True
    assert ws.resolve_item('voxel:birch_red_table')['properties']['furniture']['animation']['use'] == 'voxel:birch_red_open'
    from content_manager.editing import validate_item_shape
    for output in plan.outputs:
        if output.path.suffix == '.yml':
            for definition in yaml.safe_load(output.payload)['items'].values():
                validate_item_shape(definition)
