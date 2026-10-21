import yaml
from content_manager.core import Workspace
from test_content_manager import fixture_pack


def test_java_null_empty_false_and_list_inheritance(tmp_path):
    pack, source = fixture_pack(tmp_path)
    path = pack / 'content/items.yml'
    data = yaml.safe_load(path.read_text())
    base = data['items'].pop('oak_table')
    base.update(abstract=True, lore=['parent'], events={'interact.right': []})
    base['properties']['retained_null'] = {'value': 1}
    data['items']['base'] = base
    data['items']['oak_table'] = {'extends': 'base', 'abstract': False, 'lore': [], 'events': {}, 'properties': {'retained_null': None}}
    path.write_text(yaml.safe_dump(data))
    result = Workspace(pack).resolve_item(source)
    assert result['abstract'] is False
    assert result['lore'] == []
    assert result['events'] == {}
    assert 'retained_null' in result['properties'] and result['properties']['retained_null'] is None


def test_yaml_extension_discovery(tmp_path):
    pack, _ = fixture_pack(tmp_path)
    (pack / 'content/extra.yaml').write_text('items:\n  template:\n    abstract: true\n')
    assert 'voxel:template' in Workspace(pack).items


def test_pale_oak_available_in_1_21_4():
    from content_manager.core import _palette
    assert 'pale_oak' in _palette('wood', 'mc-1.21.4')
    assert 'pale_oak' not in _palette('wood', 'mc-1.20.5')
