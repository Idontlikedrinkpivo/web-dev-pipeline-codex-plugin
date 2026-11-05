"""Lossless local recovery and explicitly scoped portable checkpoint artifacts.

No capture command changes the source index or cleans the worktree. Restore is
explicit, validates all payload first, and accepts only the exact base or the
exact already-restored state. Workflow/chat orchestration belongs to callers.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
from typing import Iterator, Literal, TypeGuard
import uuid

from state_paths import StatePaths, contained_path, resolve_paths


Json = str | int | float | bool | None | list['Json'] | dict[str, 'Json']
PHASES = frozenset(('unit', 'wave', 'low-fix', 'final-checks', 'whole-review', 'review-fix'))
EVENTS = frozenset(('CHECKPOINT', 'HANDOVER', 'RESUME', 'COMPACT'))
REPORTS = frozenset(('work-run.md', 'resume.md', 'context-handover.md'))
STATE_FIELDS = frozenset(('run_id', 'source_id', 'unit', 'phase', 'next_action',
                          'review', 'low_batches', 'findings', 'decisions', 'reports'))
IDENTIFIER = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z')
SHA256 = re.compile(r'[0-9a-f]{64}\Z')
OBJECT_ID = re.compile(r'(?:[0-9a-f]{40}|[0-9a-f]{64})\Z')


class CheckpointError(ValueError):
    """An expected refusal; CLI callers can branch on code without parsing prose."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _is_json(value: object) -> TypeGuard[Json]:
    if value is None or isinstance(value, (str, bool, int)):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, list):
        return all(_is_json(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and _is_json(item) for key, item in value.items())
    return False


def _object(value: object, code: str = 'corrupt-payload') -> dict[str, Json]:
    if not _is_json(value) or not isinstance(value, dict):
        raise CheckpointError(code, 'expected a JSON object')
    return value


def _array(value: Json, code: str = 'corrupt-payload') -> list[Json]:
    if not isinstance(value, list):
        raise CheckpointError(code, 'expected a JSON array')
    return value


def _string(value: Json, code: str = 'corrupt-payload') -> str:
    if not isinstance(value, str):
        raise CheckpointError(code, 'expected a string')
    return value


def _encode(value: Json) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True, allow_nan=False) + '\n').encode('utf-8')


def _read_json(path: Path, code: str) -> dict[str, Json]:
    try:
        return _object(json.loads(path.read_bytes()), code)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CheckpointError(code, f'cannot read complete JSON: {path.name}') from exc


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _git(root: Path, *args: str, data: bytes | None = None,
         index: Path | None = None) -> bytes:
    env = dict(os.environ, GIT_OPTIONAL_LOCKS='0', GIT_LITERAL_PATHSPECS='1',
               GIT_CONFIG_COUNT='0')
    # Never inherit another checkout's index/object overrides from a caller.
    for key in ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_OBJECT_DIRECTORY',
                'GIT_ALTERNATE_OBJECT_DIRECTORIES', 'GIT_COMMON_DIR'):
        env.pop(key, None)
    if index is not None:
        env['GIT_INDEX_FILE'] = str(index)
    try:
        result = subprocess.run(['git', '-C', str(root), '-c', 'core.fsmonitor=false',
                                 '-c', 'core.untrackedCache=false', *args], input=data,
                                capture_output=True, env=env, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CheckpointError('capture-incomplete', 'Git command did not finish') from exc
    if result.returncode:
        raise CheckpointError('capture-incomplete', f'Git {args[0]} failed')
    return result.stdout


def _paths(checkout: Path | str, version: str, chat_key: str) -> StatePaths:
    try:
        return resolve_paths(checkout, version, chat_key)
    except ValueError as exc:
        raise CheckpointError('invalid-scope', str(exc)) from exc


def _managed(paths: StatePaths, name: str) -> bool:
    prefix = paths.plans.relative_to(paths.checkout).as_posix() + '/'
    if not name.startswith(prefix):
        return False
    tail = name[len(prefix):]
    return (tail in REPORTS or tail == 'run-state.json' or tail == 'checkpoints'
            or tail.startswith('checkpoints/') or tail.startswith('.checkpoint-tmp-'))


def _source_path(paths: StatePaths, name: str) -> Path:
    """Validate parents without following a symlink leaf (a supported payload)."""
    pure = PurePosixPath(name)
    if (not name or '\0' in name or pure.is_absolute() or pure.as_posix() != name
            or any(part in ('.', '..') or part.casefold() == '.git' for part in pure.parts)
            or _managed(paths, name)):
        raise CheckpointError('invalid-scope', 'scope must name a checkout file outside managed state')
    target = paths.checkout.joinpath(*pure.parts)
    try:
        contained_path(paths.checkout, target.parent)
    except ValueError as exc:
        raise CheckpointError('invalid-scope', 'scope has a symlink or escaping parent') from exc
    return target


@dataclass(frozen=True, slots=True)
class TreeValue:
    kind: Literal['file', 'symlink', 'missing']
    mode: int
    data: bytes


@dataclass(frozen=True, slots=True)
class IndexValue:
    mode: str
    oid: str
    data: bytes


@dataclass(frozen=True, slots=True)
class Entry:
    path: str
    tree: TreeValue
    index: IndexValue | None


@dataclass(frozen=True, slots=True)
class Observation:
    head: str
    branch: str
    plan_hash: str
    index: bytes
    dirty: tuple[str, ...]
    entries: tuple[Entry, ...]


def _tree(path: Path) -> TreeValue:
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        return TreeValue('missing', 0, b'')
    if stat.S_ISLNK(mode):
        return TreeValue('symlink', 0o777, os.fsencode(os.readlink(path)))
    if stat.S_ISREG(mode):
        return TreeValue('file', stat.S_IMODE(mode), path.read_bytes())
    raise CheckpointError('unsupported-state', 'directories, devices and sockets are not file payload')


def _index_entries(paths: StatePaths) -> dict[str, tuple[str, str]]:
    entries = {}
    for line in _git(paths.checkout, 'ls-files', '--stage', '-z').split(b'\0'):
        if not line:
            continue
        header, name = line.split(b'\t', 1)
        mode, oid, stage = header.decode('ascii').split()
        if stage != '0' or mode not in ('100644', '100755', '120000'):
            raise CheckpointError('unsupported-state', 'unmerged index and submodules need explicit resolution')
        entries[os.fsdecode(name)] = (mode, oid)
    debug = _git(paths.checkout, 'ls-files', '--debug')
    for flags in re.findall(rb'flags: ([0-9a-f]+)\n', debug):
        if int(flags, 16) & (0x20000000 | 0x40000000 | 0x8000):
            raise CheckpointError('unsupported-state', 'intent-to-add and hidden index flags are unsupported')
    return entries


def _dirty(paths: StatePaths) -> tuple[str, ...]:
    names: set[str] = set()
    for args in (('diff', '--cached', '--name-only', '--no-renames', '-z'),
                 ('diff', '--name-only', '--no-renames', '-z'),
                 ('ls-files', '--others', '--exclude-standard', '-z')):
        names.update(os.fsdecode(value) for value in _git(paths.checkout, *args).split(b'\0') if value)
    return tuple(sorted(name for name in names if not _managed(paths, name)))


def _observe(paths: StatePaths, extra: tuple[str, ...]) -> Observation:
    index = (paths.gitdir / 'index').read_bytes()
    indexed = _index_entries(paths)
    dirty = _dirty(paths)
    names = sorted(set(dirty).union(extra))
    # File/directory replacement requires a different transaction shape.
    for name in names:
        if any(parent.as_posix() in names for parent in PurePosixPath(name).parents if parent.as_posix() != '.'):
            raise CheckpointError('unsupported-state', 'overlapping file/directory payload paths')
    entries = []
    for name in names:
        path = _source_path(paths, name)
        value = indexed.get(name)
        index_value = None if value is None else IndexValue(*value, _git(paths.checkout, 'cat-file', 'blob', value[1]))
        entries.append(Entry(name, _tree(path), index_value))
    plan = contained_path(paths.checkout, paths.plans / 'plan.md')
    return Observation(_git(paths.checkout, 'rev-parse', 'HEAD').decode().strip(),
                       _git(paths.checkout, 'rev-parse', '--abbrev-ref', 'HEAD').decode().strip(),
                       _digest(plan.read_bytes()), index, dirty, tuple(entries))


def _validated_state(value: object) -> dict[str, Json]:
    state = _object(value, 'invalid-state')
    if set(state) != STATE_FIELDS:
        raise CheckpointError('invalid-state', 'provide exactly the documented portable state fields')
    for key in ('run_id', 'source_id', 'unit', 'phase', 'next_action'):
        if not _string(state[key], 'invalid-state'):
            raise CheckpointError('invalid-state', f'{key} is required')
    for key in ('run_id', 'source_id', 'unit'):
        if not IDENTIFIER.fullmatch(_string(state[key])):
            raise CheckpointError('invalid-state', 'logical identities must be stable identifiers')
    if state['phase'] not in PHASES:
        raise CheckpointError('invalid-state', 'unknown run phase')
    review = _object(state['review'], 'invalid-state')
    if set(review) != {'base', 'head'} or any(not OBJECT_ID.fullmatch(_string(review[k], 'invalid-state')) for k in review):
        raise CheckpointError('invalid-state', 'review requires full base/head object IDs')
    for key in ('low_batches', 'findings', 'decisions'):
        _array(state[key], 'invalid-state')
    reports = _object(state['reports'], 'invalid-state')
    if set(reports) != REPORTS or any(not isinstance(contents, str) for contents in reports.values()):
        raise CheckpointError('invalid-state', 'all three portable reports are required')
    # Copy nested inputs: checkpoint never mutates a caller-owned collection.
    return _object(json.loads(_encode(state)), 'invalid-state')


def _handover(event: str, successor: str | None, runtime: dict[str, Json],
              confirmed: bool, writers: bool, checks: bool) -> None:
    if event not in EVENTS or (successor is not None and not IDENTIFIER.fullmatch(successor)):
        raise CheckpointError('invalid-state', 'invalid logical event or successor')
    if event == 'CHECKPOINT' and successor is not None:
        raise CheckpointError('invalid-state', 'CHECKPOINT retains its logical owner')
    if event != 'HANDOVER':
        return
    if not (confirmed and writers and checks and successor):
        raise CheckpointError('unsafe-handover', 'confirm ownership and stop every writer/check before handover')
    owner = runtime.get('owner')
    if not isinstance(owner, dict) or owner.get('status') != 'known':
        raise CheckpointError('unsafe-handover', 'unknown or stale ownership cannot be transferred')
    for kind in ('writers', 'checks'):
        records = runtime.get(kind, [])
        if not isinstance(records, list) or any(not isinstance(item, dict) or item.get('status') != 'stopped' for item in records):
            raise CheckpointError('unsafe-handover', 'a writer/check has not been verified stopped')


@contextmanager
def _locks(paths: StatePaths) -> Iterator[Path]:
    """Exclusive creation only; never infer that somebody else's lock is stale."""
    paths.local.mkdir(parents=True, exist_ok=True)
    global_lock = contained_path(paths.gitdir, paths.gitdir / 'pipeline-work' / paths.version / 'checkpoint.lock')
    acquired: list[tuple[Path, int, int]] = []
    try:
        for lock in (global_lock, paths.local / 'checkpoint.lock', paths.gitdir / 'index.lock'):
            try:
                fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError as exc:
                raise CheckpointError('locked', 'checkpoint or Git index has an unconfirmed owner') from exc
            with os.fdopen(fd, 'wb') as stream:
                stream.write(_encode({'pid': os.getpid(), 'token': uuid.uuid4().hex}))
                info = os.fstat(stream.fileno())
                acquired.append((lock, info.st_dev, info.st_ino))
        yield paths.gitdir / 'index.lock'
    finally:
        for lock, device, inode in reversed(acquired):
            try:
                info = lock.lstat()
            except FileNotFoundError:
                continue  # restore consumed our reserved index.lock atomically
            if info.st_dev == device and info.st_ino == inode:
                lock.unlink()


def _put(folder: Path, relative: str, data: bytes, payload: dict[str, Json]) -> str:
    path = folder / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('wb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    payload[relative] = _digest(data)
    return relative


def _write_payload(folder: Path, paths: StatePaths, observed: Observation,
                   names: tuple[str, ...]) -> tuple[list[Json], dict[str, Json]]:
    folder.mkdir(parents=True)
    inventory: list[Json] = []
    payload: dict[str, Json] = {}
    for entry in observed.entries:
        if entry.path not in names:
            continue
        tree: dict[str, Json] = {'kind': entry.tree.kind, 'mode': entry.tree.mode}
        if entry.tree.kind != 'missing':
            tree['blob'] = _put(folder, 'blobs/' + _digest(entry.tree.data), entry.tree.data, payload)
        index: dict[str, Json] | None = None
        if entry.index is not None:
            index = {'mode': entry.index.mode, 'oid': entry.index.oid,
                     'blob': _put(folder, 'blobs/' + _digest(entry.index.data), entry.index.data, payload)}
        inventory.append({'path': entry.path, 'worktree': tree, 'index': index})
    for name, extra in (('staged.patch', ('--cached',)), ('unstaged.patch', ())):
        delta = b'' if not names else _git(paths.checkout, 'diff', *extra, '--binary', '--full-index',
                                          '--no-renames', '--no-ext-diff', '--no-textconv', '--', *names)
        _put(folder, name, delta, payload)
    return inventory, payload


def _fsync_dir(folder: Path) -> None:
    fd = os.open(folder, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _atomic_write(path: Path, data: bytes) -> None:
    # All writers use this same-directory temporary path, never a symlink alias.
    fd, name = tempfile.mkstemp(prefix='.checkpoint-tmp-', dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        _fsync_dir(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def _publish(paths: StatePaths, local_stage: Path, portable_stage: Path,
             manifest: dict[str, Json]) -> None:
    checkpoint_id = _string(manifest['checkpoint_id'])
    for stage in (local_stage, portable_stage):
        _fsync_dir(stage / 'blobs') if (stage / 'blobs').exists() else None
        _fsync_dir(stage)
        os.rename(stage, stage.with_name(checkpoint_id))
        _fsync_dir(stage.parent)
    for name, contents in _object(manifest['reports']).items():
        target = contained_path(paths.checkout, paths.plans / name)
        _atomic_write(target, _string(contents).encode('utf-8'))
    # This is the single authoritative publication pointer, switched LAST.
    _atomic_write(paths.plans / 'run-state.json', _encode(manifest))


def _identity(paths: StatePaths) -> dict[str, Json]:
    return {'checkout': str(paths.checkout), 'gitdir': str(paths.gitdir),
            'chat_key': paths.chat_key, 'host': socket.gethostname()}


def capture(checkout: Path | str, version: str, chat_key: str, state: object,
            owned_paths: list[str] | tuple[str, ...], *, event: str = 'CHECKPOINT',
            successor_id: str | None = None, ownership_confirmed: bool = False,
            writers_stopped: bool = False, checks_stopped: bool = False,
            runtime: object = None) -> dict[str, Json]:
    """Save full local recovery plus owned portable payload; do not stop a run."""
    paths = _paths(checkout, version, chat_key)
    portable_state = _validated_state(state)
    runtime_state = {} if runtime is None else _object(runtime, 'invalid-state')
    _handover(event, successor_id, runtime_state, ownership_confirmed, writers_stopped, checks_stopped)
    if not isinstance(owned_paths, (list, tuple)) or any(not isinstance(name, str) for name in owned_paths):
        raise CheckpointError('invalid-scope', 'owned_paths must explicitly list file paths')
    owned = tuple(sorted(set(owned_paths)))
    for name in owned:
        _source_path(paths, name)
    local_stage: Path | None = None
    portable_stage: Path | None = None
    try:
        with _locks(paths):
            observed = _observe(paths, owned)
            checkpoint_id = uuid.uuid4().hex
            local_root = contained_path(paths.gitdir, paths.local / 'checkpoints')
            portable_root = contained_path(paths.checkout, paths.plans / 'checkpoints')
            local_root.mkdir(parents=True, exist_ok=True)
            portable_root.mkdir(parents=True, exist_ok=True)
            local_stage = local_root / ('.pending-' + checkpoint_id)
            portable_stage = portable_root / ('.pending-' + checkpoint_id)
            all_names = tuple(entry.path for entry in observed.entries)
            local_inventory, local_payload = _write_payload(local_stage, paths, observed, all_names)
            inventory, payload = _write_payload(portable_stage, paths, observed, owned)
            if _observe(paths, owned) != observed:
                raise CheckpointError('concurrent-drift', 'source/index/HEAD/plan changed during capture')
            events: list[Json] = []
            current = contained_path(paths.checkout, paths.plans / 'run-state.json')
            if current.exists():
                previous = _read_json(current, 'invalid-state')
                if previous.get('schema_version') != 1 or previous.get('run_id') != portable_state['run_id']:
                    raise CheckpointError('invalid-state', 'existing checkpoint belongs to another run/schema')
                events = list(_array(previous.get('events'), 'invalid-state'))
            events.append({'event_id': uuid.uuid4().hex, 'type': event,
                           'source_id': portable_state['source_id'], 'successor_id': successor_id})
            manifest: dict[str, Json] = dict(portable_state)
            manifest.update({'schema_version': 1, 'checkpoint_id': checkpoint_id, 'version': version,
                             'head': observed.head, 'branch': observed.branch, 'plan_sha256': observed.plan_hash,
                             'completeness': {'local': True, 'portable': True, 'scope': 'owned'},
                             'paused': event == 'HANDOVER', 'events': events,
                             'inventory': inventory, 'payload': payload})
            local_manifest = dict(manifest)
            local_manifest.update({'inventory': local_inventory, 'payload': local_payload,
                                   'completeness': {'local': True, 'portable': True, 'scope': 'local'},
                                   'local_identity': _identity(paths)})
            _put(local_stage, 'runtime.json', _encode({'identity': _identity(paths), 'runtime': runtime_state}), local_payload)
            _put(local_stage, 'manifest.json', _encode(local_manifest), {})
            _put(portable_stage, 'manifest.json', _encode(manifest), {})
            _publish(paths, local_stage, portable_stage, manifest)
            return manifest
    except CheckpointError:
        raise
    except (OSError, ValueError) as exc:
        raise CheckpointError('capture-incomplete', 'checkpoint not published; retain original source/index') from exc
    finally:
        for stage in (local_stage, portable_stage):
            if stage is not None and stage.exists():
                shutil.rmtree(stage)


def _checkpoint_id(value: str) -> str:
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        raise CheckpointError('invalid-checkpoint-id', 'checkpoint identifier must be a single safe component')
    return value


def _load_payload(paths: StatePaths, source: Path, checkpoint_id: str) -> tuple[dict[str, Json], tuple[Entry, ...]]:
    if source.suffix == '.patch' or source.is_file():
        raise CheckpointError('legacy-local-only', 'legacy patches are not verified portable checkpoints')
    try:
        source = contained_path(source, source)
        manifest = _read_json(contained_path(source, source / 'manifest.json'), 'corrupt-payload')
        if manifest.get('schema_version') != 1:
            raise CheckpointError('unsupported-schema', 'checkpoint schema is not supported')
        if manifest.get('checkpoint_id') != checkpoint_id or manifest.get('version') != paths.version:
            raise CheckpointError('corrupt-payload', 'checkpoint identity/version does not match')
        completeness = _object(manifest.get('completeness'))
        scope = completeness.get('scope')
        if scope not in ('owned', 'local'):
            raise CheckpointError('corrupt-payload', 'checkpoint scope is unknown')
        if completeness.get('portable' if scope == 'owned' else 'local') is not True:
            raise CheckpointError('incomplete-checkpoint', 'checkpoint was not captured completely')
        if scope == 'local' and manifest.get('local_identity') != _identity(paths):
            raise CheckpointError('legacy-local-only', 'local recovery requires its original checkout/chat/host')
        if any(part.startswith('.pending-') for part in source.parts):
            raise CheckpointError('incomplete-checkpoint', 'pending checkpoints have not been published')
        payload = _object(manifest.get('payload'))
        if not {'staged.patch', 'unstaged.patch'}.issubset(payload):
            raise CheckpointError('corrupt-payload', 'checkpoint requires both delta layers')
        blobs: dict[str, bytes] = {}
        for name, checksum in payload.items():
            if name not in ('staged.patch', 'unstaged.patch', 'runtime.json') and not re.fullmatch(r'blobs/[0-9a-f]{64}', name):
                raise CheckpointError('corrupt-payload', 'invalid payload path')
            data = contained_path(source, source / name).read_bytes()
            if not isinstance(checksum, str) or not SHA256.fullmatch(checksum) or _digest(data) != checksum:
                raise CheckpointError('corrupt-payload', 'payload checksum mismatch')
            blobs[name] = data
        entries = []
        names: set[str] = set()
        for value in _array(manifest.get('inventory')):
            item = _object(value)
            name = _string(item.get('path'))
            _source_path(paths, name)
            if name in names:
                raise CheckpointError('corrupt-payload', 'duplicate inventory path')
            names.add(name)
            tree = _object(item.get('worktree'))
            kind = tree.get('kind')
            mode = tree.get('mode')
            if (kind not in ('file', 'symlink', 'missing') or not isinstance(mode, int)
                    or isinstance(mode, bool) or mode < 0 or mode > 0o777):
                raise CheckpointError('corrupt-payload', 'invalid worktree entry')
            tree_data = b'' if kind == 'missing' else _blob(blobs, tree.get('blob'))
            if kind == 'symlink' and (not tree_data or b'\0' in tree_data):
                raise CheckpointError('corrupt-payload', 'invalid symlink target')
            index = None
            if item.get('index') is not None:
                indexed = _object(item['index'])
                index_mode, oid = indexed.get('mode'), indexed.get('oid')
                if index_mode not in ('100644', '100755', '120000') or not isinstance(oid, str) or not OBJECT_ID.fullmatch(oid):
                    raise CheckpointError('corrupt-payload', 'invalid index entry')
                index_data = _blob(blobs, indexed.get('blob'))
                if _git(paths.checkout, 'hash-object', '--stdin', data=index_data).decode().strip() != oid:
                    raise CheckpointError('corrupt-payload', 'index object does not match its bytes')
                index = IndexValue(index_mode, oid, index_data)
            if kind == 'file':
                tree_value = TreeValue('file', mode, tree_data)
            elif kind == 'symlink':
                tree_value = TreeValue('symlink', mode, tree_data)
            else:
                tree_value = TreeValue('missing', mode, tree_data)
            entries.append(Entry(name, tree_value, index))
        for name in names:
            if any(parent.as_posix() in names for parent in PurePosixPath(name).parents):
                raise CheckpointError('corrupt-payload', 'overlapping payload paths')
        return manifest, tuple(sorted(entries, key=lambda entry: entry.path))
    except CheckpointError:
        raise
    except (OSError, ValueError) as exc:
        raise CheckpointError('corrupt-payload', 'payload is missing or outside its checkpoint directory') from exc


def _blob(blobs: dict[str, bytes], reference: Json) -> bytes:
    if not isinstance(reference, str) or not reference.startswith('blobs/') or reference not in blobs:
        raise CheckpointError('corrupt-payload', 'inventory references a missing blob')
    return blobs[reference]


def _replace_tree(path: Path, tree: TreeValue) -> None:
    if tree.kind == 'missing':
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.checkpoint-tmp-', dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, 'wb') as stream:
            if tree.kind == 'file':
                stream.write(tree.data)
                os.fchmod(stream.fileno(), tree.mode)
            stream.flush()
            os.fsync(stream.fileno())
        if tree.kind == 'symlink':
            temporary.unlink()
            temporary.symlink_to(os.fsdecode(tree.data))
        os.replace(temporary, path)
        _fsync_dir(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def _require_clean_destinations(paths: StatePaths, entries: tuple[Entry, ...]) -> None:
    """Git status omits ignored files; compare every destination with HEAD too."""
    baseline: dict[str, tuple[str, str]] = {}
    if entries:
        for line in _git(paths.checkout, 'ls-tree', '-rz', '--full-tree', 'HEAD', '--',
                         *(entry.path for entry in entries)).split(b'\0'):
            if line:
                header, name = line.split(b'\t', 1)
                mode, kind, oid = header.decode('ascii').split()
                if kind != 'blob':
                    raise CheckpointError('dirty-target', 'destination is not a baseline file')
                baseline[os.fsdecode(name)] = (mode, oid)
    for entry in entries:
        original = baseline.get(entry.path)
        if original is None:
            clean = entry.index is None and entry.tree.kind == 'missing'
        else:
            mode, oid = original
            clean = (entry.index is not None and (entry.index.mode, entry.index.oid) == original
                     and entry.tree.kind == ('symlink' if mode == '120000' else 'file'))
            if clean:
                filters = ('--path=' + entry.path,) if entry.tree.kind == 'file' else ()
                actual_oid = _git(paths.checkout, 'hash-object', *filters, '--stdin',
                                  data=entry.tree.data).decode().strip()
                clean = (actual_oid == oid and (entry.tree.kind == 'symlink'
                         or bool(entry.tree.mode & 0o100) == (mode == '100755')))
        if not clean:
            raise CheckpointError('dirty-target', 'destination differs from clean HEAD, including ignored files')


def restore(checkout: Path | str, version: str, chat_key: str, checkpoint_id: str, *,
            source: Path | str | None = None) -> dict[str, Json]:
    """Validate then restore a clean exact base; never reapply to a partial tree."""
    checkpoint_id = _checkpoint_id(checkpoint_id)
    paths = _paths(checkout, version, chat_key)
    folder = paths.local / 'checkpoints' / checkpoint_id if source is None else Path(os.path.abspath(source))
    manifest, expected = _load_payload(paths, folder, checkpoint_id)
    names = tuple(entry.path for entry in expected)
    try:
        with _locks(paths) as index_lock:
            actual_head = _git(paths.checkout, 'rev-parse', 'HEAD').decode().strip()
            if actual_head != manifest.get('head'):
                raise CheckpointError('wrong-base', 'switch explicitly to the captured full HEAD before restoring')
            plan = contained_path(paths.checkout, paths.plans / 'plan.md')
            if _digest(plan.read_bytes()) != manifest.get('plan_sha256'):
                raise CheckpointError('wrong-plan', 'the checkout plan differs from the captured plan')
            before = _observe(paths, names)
            selected = tuple(entry for entry in before.entries if entry.path in names)
            if selected == expected and set(before.dirty).issubset(names):
                return {'status': 'already-restored', 'checkpoint_id': checkpoint_id}
            if before.dirty:
                raise CheckpointError('dirty-target', 'target is partial or divergent; preserve it and stop')
            _require_clean_destinations(paths, selected)
            with tempfile.TemporaryDirectory(prefix='restore-', dir=paths.local) as temporary:
                prepared = Path(temporary) / 'index'
                prepared.write_bytes(before.index)
                for entry in expected:
                    if entry.index is None:
                        _git(paths.checkout, 'update-index', '--force-remove', '--', entry.path, index=prepared)
                    else:
                        _git(paths.checkout, 'hash-object', '-w', '--stdin', data=entry.index.data)
                        _git(paths.checkout, 'update-index', '--add', '--cacheinfo', entry.index.mode,
                             entry.index.oid, entry.path, index=prepared)
                if _observe(paths, names) != before:
                    raise CheckpointError('dirty-target', 'target changed during restore preflight')
                journal = paths.local / 'restore-in-progress.json'
                _atomic_write(journal, _encode({'checkpoint_id': checkpoint_id, 'head': actual_head,
                                               'paths': list(names)}))
                try:
                    original = {entry.path: entry.tree for entry in before.entries}
                    for entry in expected:
                        target = _source_path(paths, entry.path)
                        if _tree(target) != original[entry.path]:
                            raise CheckpointError('dirty-target', 'writer changed a target during restore')
                        _replace_tree(target, entry.tree)
                    after = _observe(paths, names)
                    if (after.head != before.head or after.plan_hash != before.plan_hash
                            or after.index != before.index or not set(after.dirty).issubset(names)
                            or any(_tree(_source_path(paths, entry.path)) != entry.tree for entry in expected)):
                        raise CheckpointError('dirty-target', 'target changed during restore; preserve partial state')
                    with index_lock.open('wb') as stream:
                        stream.write(prepared.read_bytes())
                        stream.flush()
                        os.fsync(stream.fileno())
                    os.replace(index_lock, paths.gitdir / 'index')
                    _fsync_dir(paths.gitdir)
                    journal.unlink()
                except OSError as exc:
                    raise CheckpointError('restore-incomplete', 'restore interrupted; keep partial state and local journal') from exc
            return {'status': 'restored', 'checkpoint_id': checkpoint_id}
    except CheckpointError:
        raise
    except (OSError, ValueError) as exc:
        raise CheckpointError('restore-incomplete', 'restore could not finish; no blind rollback was attempted') from exc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    capture_parser = commands.add_parser('capture')
    restore_parser = commands.add_parser('restore')
    for command in (capture_parser, restore_parser):
        command.add_argument('--checkout', type=Path, required=True)
        command.add_argument('--version', required=True)
        command.add_argument('--chat-key', required=True)
    capture_parser.add_argument('--state', type=Path, required=True)
    capture_parser.add_argument('--owned', action='append', default=[])
    capture_parser.add_argument('--runtime', type=Path)
    capture_parser.add_argument('--event', default='CHECKPOINT', choices=sorted(EVENTS))
    capture_parser.add_argument('--successor-id')
    for flag in ('ownership-confirmed', 'writers-stopped', 'checks-stopped'):
        capture_parser.add_argument('--' + flag, action='store_true')
    restore_parser.add_argument('--checkpoint-id', required=True)
    restore_parser.add_argument('--source', type=Path)
    args = parser.parse_args()
    try:
        if args.command == 'capture':
            runtime = None if args.runtime is None else _read_json(args.runtime, 'invalid-state')
            result = capture(args.checkout, args.version, args.chat_key, _read_json(args.state, 'invalid-state'),
                             args.owned, event=args.event, successor_id=args.successor_id,
                             ownership_confirmed=args.ownership_confirmed, writers_stopped=args.writers_stopped,
                             checks_stopped=args.checks_stopped, runtime=runtime)
        else:
            result = restore(args.checkout, args.version, args.chat_key, args.checkpoint_id, source=args.source)
        sys.stdout.buffer.write(_encode(result))
        return 0
    except CheckpointError as exc:
        sys.stdout.buffer.write(_encode({'error': exc.code, 'message': str(exc)}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
