import json
import pytest
import yaml

from content_manager.assets import ModelResolver, ReferenceGraph, item_references, resource_id
from content_manager.core import Workspace, ContentError, apply_plan, plan_family
from test_content_manager import fixture_pack


def inherited_model(pack):
    source = pack / 'assets/voxel/models/furniture/oak_table.json'
    base = source.with_name('base.json')
    original = json.loads(source.read_text())
    original['display'] = {'gui': {'rotation': [30, 225, 0], 'scale': [0.5, 0.5, 0.5]}}
    original['elements'][0]['faces']['up']['uv'] = [1, 2, 3, 4]
    base.write_text(json.dumps(original))
    source.write_text(json.dumps({'parent': 'voxel:furniture/base', 'textures': {'accent': '#wood'}}))
    return source, base, original


@pytest.mark.parametrize('strategy', ['alias', 'clone'])
def test_inherited_geometry_textures_and_transforms_preserved(tmp_path, strategy):
    pack, source = fixture_pack(tmp_path)
    src, base, original = inherited_model(pack)
    ws = Workspace(pack)
    plan = plan_family(ws, source, 'wood', strategy=strategy, selected=('spruce',))
    apply_plan(plan)
    result = ModelResolver(Workspace(pack)).resolve('voxel:furniture/spruce_table')
    assert result.effective['elements'] == original['elements']
    assert result.effective['display'] == original['display']
    assert result.textures['wood'] == 'minecraft:block/spruce_planks'
    assert result.textures['accent'] == 'minecraft:block/spruce_planks'
    assert result.textures['particle'] == 'minecraft:block/spruce_planks'


def test_model_ancestor_edit_invalidates_preview(tmp_path):
    pack, source = fixture_pack(tmp_path)
    _, base, _ = inherited_model(pack)
    plan = plan_family(Workspace(pack), source, 'wood', selected=('spruce',))
    base.write_text(base.read_text() + '\n')
    with pytest.raises(ContentError, match='dependency'):
        apply_plan(plan)


@pytest.mark.parametrize('model, message', [
    ({'parent': 'voxel:furniture/oak_table'}, 'parent cycle'),
    ({'parent': 'voxel:furniture/missing'}, 'Missing model'),
    ({'textures': {'a': '#b', 'b': '#a'}}, 'alias cycle'),
    ({'textures': {'a': '#missing'}}, 'Missing/invalid texture'),
    ({'textures': []}, 'textures must be'),
])
def test_bad_models_fail_explicitly(tmp_path, model, message):
    pack, _ = fixture_pack(tmp_path)
    (pack / 'assets/voxel/models/furniture/oak_table.json').write_text(json.dumps(model))
    with pytest.raises(ContentError, match=message):
        ModelResolver(Workspace(pack)).resolve('voxel:furniture/oak_table')


def test_vanilla_parent_is_external_not_invented(tmp_path):
    pack, _ = fixture_pack(tmp_path)
    (pack / 'assets/voxel/models/furniture/oak_table.json').write_text(json.dumps({'parent': 'item/generated', 'textures': {'layer0': 'minecraft:item/paper'}}))
    result = ModelResolver(Workspace(pack)).resolve('voxel:furniture/oak_table')
    assert result.external_parents == ('minecraft:item/generated',)
    assert 'elements' not in result.effective


def test_graph_incoming_missing_texture_and_unused(tmp_path):
    pack, _ = fixture_pack(tmp_path)
    source = pack / 'assets/voxel/models/furniture/oak_table.json'
    model = json.loads(source.read_text())
    model['textures']['wood'] = 'voxel:missing'
    source.write_text(json.dumps(model))
    source.with_name('unused.json').write_text(json.dumps(model))
    graph = ReferenceGraph(Workspace(pack))
    assert graph.incoming('model:voxel:furniture/oak_table')[0].source == 'item:voxel:oak_table'
    assert any('Missing texture' in d for d in graph.diagnostics)
    assert 'model:voxel:furniture/unused' in graph.unused_candidates()
    assert graph.duplicate_models() == [['voxel:furniture/oak_table', 'voxel:furniture/unused']]


def linked_pack(tmp_path, vehicle=False):
    pack, source = fixture_pack(tmp_path)
    path = pack / 'content/items.yml'
    data = yaml.safe_load(path.read_text())
    owner = data['items']['oak_table']
    if vehicle:
        owner['properties'] = {'vehicle': {'type': 'LAND', 'model_item': 'oak_table', 'drop': 'oak_table', 'inventory': {'preview_item': 'oak_open', 'chest': {'item': 'CHEST', 'preview_item': 'oak_open', 'visual': {'mode': 'MODEL_SWAP', 'model_item': 'oak_open'}}}}}
    else:
        owner['properties']['furniture'].update(model_item='oak_table', drop='oak_table',
            animation={'use': 'oak_open', 'close_delay': 20},
            blockstates=[{'neighbors': ['north'], 'absent': ['south'], 'model_item': 'oak_open', 'rotation': 90, 'relative': True}],
            display_parts={'top': {'type': 'item', 'model_item': 'oak_open'}},
            interaction={'commands': [{'command': 'say oak_table', 'executor': 'console'}]})
    data['items']['oak_open'] = {'abstract': True, 'material': 'paper', 'render': {'model': 'voxel:furniture/oak_open'}}
    path.write_text(yaml.safe_dump(data))
    model = pack / 'assets/voxel/models/furniture/oak_table.json'
    model.with_name('oak_open.json').write_bytes(model.read_bytes())
    return pack, source


@pytest.mark.parametrize('vehicle', [False, True])
def test_dependency_fanout_is_typed_abstract_and_idempotent(tmp_path, vehicle):
    pack, source = linked_pack(tmp_path, vehicle)
    plan = plan_family(Workspace(pack), source, 'wood', selected=('spruce',), include_dependencies=True)
    assert len(plan.changed) == 5
    apply_plan(plan)
    ws = Workspace(pack)
    owner = ws.resolve_item('voxel:spruce_table')
    state = ws.resolve_item('voxel:spruce_open')
    assert state['abstract'] is True
    assert owner['abstract'] is False
    refs = item_references(owner, 'voxel')
    assert {r.target for r in refs} == {'voxel:spruce_table', 'voxel:spruce_open'}
    if vehicle:
        assert owner['properties']['vehicle']['inventory']['chest']['item'] == 'CHEST'
    else:
        furniture = owner['properties']['furniture']
        assert furniture['blockstates'][0]['neighbors'] == ['north']
        assert furniture['blockstates'][0]['rotation'] == 90
        assert furniture['interaction']['commands'][0]['command'] == 'say oak_table'
        authored = ws.items['voxel:spruce_table'].definition['properties']['furniture']
        assert 'rotation_step' not in authored
        assert authored['animation'] == {'use': 'voxel:spruce_open'}
    assert not plan_family(ws, source, 'wood', selected=('spruce',), include_dependencies=True).changed


def test_missing_related_item_blocks_generation(tmp_path):
    pack, source = linked_pack(tmp_path)
    path = pack / 'content/items.yml'
    data = yaml.safe_load(path.read_text())
    del data['items']['oak_open']
    path.write_text(yaml.safe_dump(data))
    with pytest.raises(ContentError, match='Missing item reference'):
        plan_family(Workspace(pack), source, 'wood', selected=('spruce',), include_dependencies=True)


def test_all_sixteen_wool_colors(tmp_path):
    pack, source = fixture_pack(tmp_path, kind='vehicle')
    apply_plan(plan_family(Workspace(pack), source, 'wool'))
    ws = Workspace(pack)
    assert len(ws.items) == 16
    from content_manager.core import COLORS
    for color in COLORS:
        model = ModelResolver(ws).resolve(f'voxel:furniture/{color}_wool_chair')
        assert model.textures['wool'] == f'minecraft:block/{color}_wool'


def test_unowned_identical_file_is_not_silently_adopted(tmp_path):
    pack, source = fixture_pack(tmp_path)
    plan = plan_family(Workspace(pack), source, 'wood', selected=('spruce',))
    model = plan.outputs[1]
    model.path.write_bytes(model.payload)
    with pytest.raises(ContentError, match='unowned'):
        plan_family(Workspace(pack), source, 'wood', selected=('spruce',))


@pytest.mark.parametrize('ref', ['voxel:../x', 'voxel:/a', 'voxel:a//b', 'voxel:a\\b', 'voxel:a:b'])
def test_resource_path_rejection(ref):
    with pytest.raises(ContentError):
        resource_id(ref)
