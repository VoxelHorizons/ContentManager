import json
import subprocess
import sys

import pytest

from content_manager.core import ContentError, Workspace, apply_plan, plan_family, rollback_snapshot
from content_manager import transactions as tx
from test_content_manager import fixture_pack


def make_plan(tmp_path):
    pack, source = fixture_pack(tmp_path)
    return pack, plan_family(Workspace(pack.parent), source, 'wood', selected=('oak', 'spruce'))


def test_rollback_redo_exact_bytes(tmp_path):
    pack, plan = make_plan(tmp_path)
    snapshot = apply_plan(plan)
    outputs = {p.path: p.payload for p in plan.changed}
    tx.restore(pack, snapshot)
    assert all(not p.exists() for p in outputs)
    tx.restore(pack, snapshot, redo=True)
    assert {p: p.read_bytes() for p in outputs} == outputs


def test_failed_write_restores_all_outputs(tmp_path, monkeypatch):
    pack, plan = make_plan(tmp_path)
    original = tx.write_atomic
    count = 0
    def fail(path, payload):
        nonlocal count
        if path in [f.path for f in plan.changed]:
            count += 1
            if count == 2:
                raise OSError('disk full')
        original(path, payload)
    monkeypatch.setattr(tx, 'write_atomic', fail)
    with pytest.raises(OSError, match='disk full'):
        apply_plan(plan)
    assert all(not f.path.exists() for f in plan.changed)
    assert not tx.pending_snapshots(pack)


def test_interrupted_write_is_explicitly_recoverable(tmp_path, monkeypatch):
    pack, plan = make_plan(tmp_path)
    original = tx.write_atomic
    def crash(path, payload):
        original(path, payload)
        if path == plan.changed[0].path:
            raise KeyboardInterrupt('simulated process loss')
    monkeypatch.setattr(tx, 'write_atomic', crash)
    with pytest.raises(KeyboardInterrupt):
        apply_plan(plan)
    pending = tx.pending_snapshots(pack)
    assert len(pending) == 1
    with pytest.raises(ContentError, match='Unfinished'):
        apply_plan(plan)
    monkeypatch.setattr(tx, 'write_atomic', original)
    tx.restore(pack, pending[0], recover=True)
    assert all(not f.path.exists() for f in plan.changed)
    assert not tx.pending_snapshots(pack)


def test_corrupt_backup_does_not_partially_rollback(tmp_path):
    pack, plan = make_plan(tmp_path)
    apply_plan(plan)
    # Force a legitimate recipe-owned model update so snapshot has originals.
    model = pack / 'assets/voxel/models/furniture/oak_table.json'
    data = json.loads(model.read_text())
    # Clone strategy cannot replace alias recipe, so modify a generated payload via
    # a new approved Plan with the current hash precondition.
    from dataclasses import replace
    from content_manager.core import _sha
    output = plan.outputs[0]
    changed = replace(output, payload=output.payload + b'# revised\n', baseline_sha=_sha(output.payload), status='update')
    plan.outputs = [changed]
    plan.workspace_inventory = Workspace(pack).input_hashes
    snapshot = apply_plan(plan)
    backup = snapshot / 'originals' / changed.path.relative_to(pack)
    backup.write_bytes(b'corrupted')
    before = changed.path.read_bytes()
    with pytest.raises(ContentError, match='Corrupt backup'):
        rollback_snapshot(pack, snapshot)
    assert changed.path.read_bytes() == before


def test_lock_excludes_separate_process_and_releases(tmp_path):
    pack, _ = make_plan(tmp_path)
    code = "from pathlib import Path; from content_manager.transactions import writer_lock; import sys\nwith writer_lock(Path(sys.argv[1])): pass"
    with tx.writer_lock(pack):
        result = subprocess.run([sys.executable, '-c', code, str(pack)], capture_output=True, text=True)
        assert result.returncode != 0
        assert 'writer holds' in result.stderr
    result = subprocess.run([sys.executable, '-c', code, str(pack)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('relative', ['../escape', '/absolute', 'content/CON.yml', 'content/a./b.yml', 'content/a\\b.yml', 'content/C:/a', 'content//a', 'content/../a'])
def test_portable_path_rejections(tmp_path, relative):
    with pytest.raises(ContentError):
        tx.portable_path(tmp_path, relative)


def test_case_collision(tmp_path):
    (tmp_path / 'Content').mkdir()
    with pytest.raises(ContentError, match='collision'):
        tx.portable_path(tmp_path, 'content/items.yml')


def test_new_duplicate_definition_invalidates_plan(tmp_path):
    pack, plan = make_plan(tmp_path)
    (pack / 'content/external.yaml').write_text('items:\n  spruce_table: {}\n')
    with pytest.raises(ContentError, match='definitions changed'):
        apply_plan(plan)
    assert not plan.outputs[0].path.exists()


def test_ancestor_file_change_invalidates_plan(tmp_path):
    pack, source = fixture_pack(tmp_path)
    (pack / 'content/parent.yml').write_text('items:\n  base:\n    properties: {furniture: {rotation_step: 90}}\n')
    import yaml
    path = pack / 'content/items.yml'
    data = yaml.safe_load(path.read_text())
    data['items']['oak_table']['extends'] = 'base'
    path.write_text(yaml.safe_dump(data))
    plan = plan_family(Workspace(pack.parent), source, 'wood', selected=('spruce',))
    (pack / 'content/parent.yml').write_text('items:\n  base:\n    properties: {furniture: {rotation_step: 45}}\n')
    with pytest.raises(ContentError, match='dependency'):
        apply_plan(plan)


def test_stale_workspace_rejected_at_plan_time(tmp_path):
    pack, source = fixture_pack(tmp_path)
    ws = Workspace(pack.parent)
    with (pack / 'content/items.yml').open('a') as stream:
        stream.write('# external edit\n')
    with pytest.raises(ContentError, match='since scan'):
        plan_family(ws, source, 'wood', selected=('spruce',))


def test_metadata_symlink_cannot_escape(tmp_path):
    pack, plan = make_plan(tmp_path)
    external = tmp_path / 'external'
    external.mkdir()
    try:
        (pack / '.contentmanager').symlink_to(external, target_is_directory=True)
    except OSError:
        pytest.skip('symlink privilege unavailable')
    with pytest.raises(ContentError, match='escapes|Symlink'):
        apply_plan(plan)
    assert list(external.iterdir()) == []


def test_runtime_allocations_protected(tmp_path):
    for name in tx.PROTECTED:
        with pytest.raises(ContentError, match='Protected'):
            tx.writable_path(tmp_path, 'content/' + name)


def test_interrupted_rollback_is_resumable(tmp_path, monkeypatch):
    pack, plan = make_plan(tmp_path)
    snapshot = apply_plan(plan)
    original = tx.sync_dir
    calls = 0
    def crash(path):
        nonlocal calls
        original(path)
        # First sync persists restore state; second follows the first deletion.
        calls += 1
        if calls == 2:
            raise KeyboardInterrupt('interrupted rollback')
    monkeypatch.setattr(tx, 'sync_dir', crash)
    with pytest.raises(KeyboardInterrupt):
        rollback_snapshot(pack, snapshot)
    assert tx.pending_snapshots(pack) == [snapshot]
    monkeypatch.setattr(tx, 'sync_dir', original)
    tx.restore(pack, snapshot, recover=True)
    assert all(not f.path.exists() for f in plan.changed)


def test_corrupt_late_backup_blocks_all_restore_writes(tmp_path):
    from dataclasses import replace
    from content_manager.core import _sha
    pack, plan = make_plan(tmp_path)
    apply_plan(plan)
    plan.workspace_inventory = Workspace(pack).input_hashes
    changed = [replace(f, payload=f.payload + b'\n', baseline_sha=_sha(f.payload), status='update') for f in plan.outputs[:2]]
    plan.outputs = changed
    snapshot = apply_plan(plan)
    # Original implementation restored the last record before discovering this.
    backup = snapshot / 'originals' / changed[0].path.relative_to(pack)
    backup.write_bytes(b'corrupt')
    before = {f.path: f.path.read_bytes() for f in changed}
    with pytest.raises(ContentError, match='Corrupt backup'):
        rollback_snapshot(pack, snapshot)
    assert {p: p.read_bytes() for p in before} == before
