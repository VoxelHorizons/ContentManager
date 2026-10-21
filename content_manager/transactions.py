"""Recoverable offline file transactions. Locks coordinate Content Manager writers.

External editors do not share the lock: optimistic hashes remain mandatory.
A journal is durable before the first content write; recovery is explicit.
"""
from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path, PurePosixPath
import stat
import time

from .core import ContentError, _ensure_inside, _sha, _serialize_json

PROTECTED = {'render-allocations.yml', 'block-allocations.yml', 'glyph-allocations.yml'}


def portable_path(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or '\\' in relative or ':' in relative:
        raise ContentError(f'Non-portable path: {relative!r}')
    parts = PurePosixPath(relative).parts
    if not parts or relative.startswith('/') or any(p in ('', '.', '..') for p in relative.split('/')):
        raise ContentError(f'Unsafe relative path: {relative!r}')
    for part in parts:
        stem = part.split('.')[0].upper()
        if (part.endswith((' ', '.')) or any(c in part for c in '<>"|?*')
                or any(ord(c) < 32 for c in part)
                or stem in {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}):
            raise ContentError(f'Non-portable filename: {part}')
    path = _ensure_inside(root, root.joinpath(*parts))
    cursor = root
    for part in parts:
        if cursor.is_dir():
            for sibling in cursor.iterdir():
                if sibling.name.casefold() == part.casefold() and sibling.name != part:
                    raise ContentError(f'Case-insensitive path collision: {sibling}')
        cursor /= part
    return path


def writable_path(root: Path, relative: str) -> Path:
    path = portable_path(root, relative)
    parts = PurePosixPath(relative).parts
    if path.name.lower() in PROTECTED or not (parts[0] in ('content', 'assets') or parts[:2] == ('.contentmanager', 'manifests')):
        raise ContentError(f'Protected or non-authored output path: {relative}')
    return path


def read_bytes(path: Path) -> bytes | None:
    if path.exists() and not path.is_file():
        raise ContentError(f'Expected regular file: {path}')
    return path.read_bytes() if path.exists() else None


def digest(data):
    return _sha(data) if data is not None else None


def sync_dir(path: Path):
    # Windows does not expose a portable directory fsync through Python.
    if os.name != 'nt':
        fd = os.open(path, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def write_atomic(path: Path, payload: bytes):
    import tempfile
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else None
    fd, temp = tempfile.mkstemp(prefix='.cm-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        if mode is not None:
            os.chmod(temp, mode)
        os.replace(temp, path)
        sync_dir(path.parent)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


@contextmanager
def writer_lock(root: Path):
    root = root.resolve()
    lock = portable_path(root, '.contentmanager/write.lock')
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open('a+b') as stream:
        if stream.tell() == 0:
            stream.write(b'0')
            stream.flush()
        stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise ContentError('Another Content Manager writer holds this pack lock') from exc
        try:
            yield
        finally:
            if os.name == 'nt':
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


def pending_snapshots(root: Path):
    folder = portable_path(root, '.contentmanager/backups')
    if not folder.exists():
        return []
    pending = []
    for journal in sorted(folder.glob('*/snapshot.json')):
        _ensure_inside(root, journal)
        try:
            data = json.loads(journal.read_text(encoding='utf-8'))
            if data.get('state', 'committed') not in ('committed', 'rolled_back'):
                pending.append(journal.parent)
        except (ValueError, AttributeError) as exc:
            raise ContentError(f'Unreadable recovery journal: {journal}') from exc
    return pending


def apply(plan):
    root = plan.pack.root
    with writer_lock(root):
        pending = pending_snapshots(root)
        if pending:
            raise ContentError(f'Unfinished transaction; recover before applying: {pending[0]}')
        for path, expected in plan.input_hashes.items():
            if digest(read_bytes(path)) != expected:
                raise ContentError(f'Source item or model changed after preview (dependency): {path}')
        # Detect newly introduced definitions and removed files as well as edits.
        if plan.workspace_inventory is not None:
            from .core import Workspace
            current = Workspace(plan.workspace_root or root)
            if current.input_hashes != plan.workspace_inventory:
                raise ContentError('Workspace definitions changed after preview; refresh plan')
        seen, originals = set(), {}
        for output in plan.outputs:
            relative = output.path.relative_to(root).as_posix()
            path = writable_path(root, relative)
            if relative.casefold() in seen:
                raise ContentError(f'Duplicate output path: {relative}')
            seen.add(relative.casefold())
            prior = read_bytes(path)
            if digest(prior) != output.baseline_sha:
                raise ContentError(f'File changed after preview: {path}')
            originals[path] = prior
        if not plan.changed:
            return None
        snapshot = portable_path(root, f'.contentmanager/backups/{time.time_ns()}_{plan.recipe_key}')
        snapshot.mkdir(parents=True, exist_ok=False)
        records = []
        for output in plan.changed:
            relative = output.path.relative_to(root).as_posix()
            prior = originals[output.path]
            if prior is not None:
                write_atomic(snapshot / 'originals' / relative, prior)
            write_atomic(snapshot / 'after' / relative, output.payload)
            records.append({'path': relative, 'before_sha256': digest(prior), 'after_sha256': _sha(output.payload)})
        journal = {'schema': 2, 'state': 'applying', 'changes': records}
        write_atomic(snapshot / 'snapshot.json', _serialize_json(journal))
        try:
            for output in plan.changed:
                writable_path(root, output.path.relative_to(root).as_posix())
                write_atomic(output.path, output.payload)
            journal['state'] = 'committed'
            write_atomic(snapshot / 'snapshot.json', _serialize_json(journal))
        except Exception as exc:
            try:
                _restore(root, snapshot, 'before', recovery=True)
            except Exception as recovery_error:
                raise ContentError(f'Apply failed; recovery required at {snapshot}: {recovery_error}') from exc
            raise
        return snapshot


def _restore(root: Path, snapshot: Path, direction: str, recovery=False):
    snapshot = _ensure_inside(root, snapshot)
    backups = portable_path(root, '.contentmanager/backups')
    if snapshot.parent != backups:
        raise ContentError('Snapshot must be directly inside .contentmanager/backups')
    journal_path = _ensure_inside(root, snapshot / 'snapshot.json')
    data = json.loads(journal_path.read_text(encoding='utf-8'))
    if not isinstance(data, dict) or data.get('schema') not in (1, 2) or not isinstance(data.get('changes'), list):
        raise ContentError('Invalid snapshot schema')
    if direction == 'after' and data.get('schema') != 2:
        raise ContentError('Legacy snapshots do not contain redo payloads')
    prepared, seen = [], set()
    for record in data['changes']:
        relative = record['path']
        path = writable_path(root, relative)
        if relative.casefold() in seen:
            raise ContentError(f'Duplicate snapshot path: {relative}')
        seen.add(relative.casefold())
        before, after = record['before_sha256'], record['after_sha256']
        for value in (before, after):
            if value is not None and (not isinstance(value, str) or len(value) != 64 or any(c not in '0123456789abcdef' for c in value)):
                raise ContentError('Invalid snapshot hash')
        expected = after if direction == 'before' else before
        current = digest(read_bytes(path))
        if current not in ({before, after} if recovery else {expected}):
            raise ContentError(f'Cannot rollback/redo; file changed since apply: {path}')
        desired = before if direction == 'before' else after
        payload = None
        if desired is not None:
            backup = _ensure_inside(root, snapshot / ('originals' if direction == 'before' else 'after') / relative)
            payload = read_bytes(backup)
            if digest(payload) != desired:
                raise ContentError(f'Corrupt backup; cannot rollback: {backup}')
        prepared.append((path, payload))
    # ALL backups and targets verified before modifying anything.
    data['schema'] = data.get('schema', 1)
    data['state'] = 'restoring_before' if direction == 'before' else 'restoring_after'
    write_atomic(journal_path, _serialize_json(data))
    for path, payload in reversed(prepared):
        writable_path(root, path.relative_to(root).as_posix())
        if payload is None:
            if path.exists():
                path.unlink()
                sync_dir(path.parent)
        else:
            write_atomic(path, payload)
    data['state'] = 'rolled_back' if direction == 'before' else 'committed'
    write_atomic(journal_path, _serialize_json(data))


def restore(pack_root, snapshot_dir, *, redo=False, recover=False):
    root = Path(pack_root).resolve()
    with writer_lock(root):
        snapshot = Path(snapshot_dir).absolute()
        pending = pending_snapshots(root)
        if pending and (not recover or any(p != snapshot for p in pending)):
            raise ContentError(f'Unfinished transaction; recover first: {pending[0]}')
        direction = 'after' if redo else 'before'
        if recover:
            data = json.loads((snapshot / 'snapshot.json').read_text(encoding='utf-8'))
            if data.get('state') == 'restoring_after':
                direction = 'after'
        _restore(root, snapshot, direction, recovery=recover)
