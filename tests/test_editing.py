import copy
import pytest
import yaml
from content_manager.core import ContentError, Workspace, apply_plan, rollback_snapshot
from content_manager.editing import parse_item_text, plan_edit_item
from test_content_manager import fixture_pack


def test_roundtrip_comments_quotes_siblings_and_restore(tmp_path):
    pack, source = fixture_pack(tmp_path)
    path = pack / 'content/items.yml'
    path.write_text('''# file comment
items:
  oak_table:
    material: "minecraft:paper" # carrier
    display_name: '&fOak Table' # name
    render:
      model: voxel:furniture/oak_table
    properties:
      future_extension: {keep: true} # unknown extension preserved
  sibling: # sibling comment
    material: paper
    lore: ["do not touch"]
''')
    before = path.read_bytes()
    ws = Workspace(pack)
    edited = copy.deepcopy(ws.items[source].definition)
    edited['display_name'] = '&aOak Table'
    snapshot = apply_plan(plan_edit_item(ws, source, edited))
    text = path.read_text()
    assert '# file comment' in text and '# carrier' in text and '# name' in text
    assert "'&aOak Table'" in text and '"minecraft:paper"' in text
    assert '# sibling comment' in text and '# unknown extension preserved' in text
    assert yaml.safe_load(text)['items']['sibling'] == yaml.safe_load(before)['items']['sibling']
    rollback_snapshot(pack, snapshot)
    assert path.read_bytes() == before


def test_noop_is_byte_exact_including_crlf_bom(tmp_path):
    pack, source = fixture_pack(tmp_path)
    path = pack / 'content/items.yml'
    raw = b'\xef\xbb\xbf' + path.read_bytes().replace(b'\n', b'\r\n')
    path.write_bytes(raw)
    ws = Workspace(pack)
    plan = plan_edit_item(ws, source, ws.items[source].definition)
    assert plan.outputs[0].payload == raw
    assert not plan.changed


def test_alias_reads_but_edits_refused(tmp_path):
    pack, source = fixture_pack(tmp_path)
    path = pack / 'content/items.yml'
    path.write_text('items:\n  base: &base\n    material: paper\n  oak_table:\n    <<: *base\n    display_name: Oak\n')
    ws = Workspace(pack)
    assert ws.items[source].definition['material'] == 'paper'
    edited = dict(ws.items[source].definition, display_name='New')
    with pytest.raises(ContentError, match='read-only'):
        plan_edit_item(ws, source, edited)


def test_editor_rejects_new_inheritance_cycle(tmp_path):
    pack, source = fixture_pack(tmp_path)
    ws = Workspace(pack)
    edited = dict(ws.items[source].definition, extends=source)
    with pytest.raises(ContentError, match='cycle'):
        plan_edit_item(ws, source, edited)


@pytest.mark.parametrize('text', ['abstract: yesplease', 'lore: hello', 'render: {durability: -1}', 'properties: null', 'invalid_key: 1', 'render: {attributes: {hide: 1}}'])
def test_invalid_item_shape(text):
    with pytest.raises(ContentError):
        parse_item_text(text)


def test_edit_stale_external_file_refused(tmp_path):
    pack, source = fixture_pack(tmp_path)
    ws = Workspace(pack)
    (pack / 'content/items.yml').write_text('items: {}\n')
    with pytest.raises(ContentError, match='changed since scan'):
        plan_edit_item(ws, source, ws.items[source].definition)
