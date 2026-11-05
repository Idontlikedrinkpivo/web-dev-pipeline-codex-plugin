"""Checkout-owned portable plans and chat-owned local state; no directory creation.

Git's common directory is metadata for legacy validation only. New runtime state
always belongs to --absolute-git-dir, which differs for every linked worktree.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess


def _git(checkout: Path, *args: str) -> str:
    try:
        result = subprocess.run(['git', '-C', str(checkout), *args],
                                capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError(f'cannot resolve Git checkout {checkout}: {exc}') from exc
    if result.returncode or not result.stdout.strip():
        raise ValueError(f'not a usable Git checkout: {checkout}')
    return result.stdout.strip()


def checkout_root(checkout: Path | str) -> Path:
    """Resolve a real, existing checkout, including a directory nested inside it."""
    try:
        given = Path(checkout).resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ValueError(f'missing or invalid checkout: {checkout}') from exc
    if not given.is_dir():
        raise ValueError(f'checkout must be a directory: {checkout}')
    return Path(_git(given, 'rev-parse', '--show-toplevel')).resolve()


def contained_path(root: Path, path: Path) -> Path:
    """Require lexical containment and stable physical ownership, even if absent.

    Managed state never follows symlink aliases: an internal alias can also lead
    into a different checkout or a different chat's state inside the same root.
    """
    base = root.resolve()
    candidate = Path(os.path.abspath(path))
    try:
        candidate.relative_to(base)
        physical = candidate.resolve()
        physical.relative_to(base)
    except (ValueError, OSError, RuntimeError) as exc:
        raise ValueError(f'path outside state root {base}: {path}') from exc
    if candidate != physical:
        raise ValueError(f'symlink in checkout state path: {path}')
    return candidate


def plans_root(checkout: Path | str) -> Path:
    root = checkout_root(checkout)
    return contained_path(root, root / 'documentation' / 'plans')


def portable_plans(checkout: Path | str, version: str) -> Path:
    if not re.fullmatch(r'\d+(?:\.\d+)*', version):
        raise ValueError(f'invalid iteration version: {version!r}')
    root = checkout_root(checkout)
    return contained_path(root, root / 'documentation' / 'plans' / version)


@dataclass(frozen=True)
class StatePaths:
    checkout: Path
    plans: Path
    local: Path
    gitdir: Path
    common_dir: Path
    version: str
    chat_key: str


def resolve_paths(checkout: Path | str, version: str, chat_key: str) -> StatePaths:
    """Resolve portable/local roots without falling back to a foreign checkout."""
    root = checkout_root(checkout)
    plans = portable_plans(root, version)
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', chat_key):
        raise ValueError('invalid chat key; set CODEX_THREAD_ID to this chat identity')
    gitdir = Path(_git(root, 'rev-parse', '--absolute-git-dir')).resolve()
    common = Path(_git(root, 'rev-parse', '--path-format=absolute', '--git-common-dir')).resolve()
    # Fixed lowercase encoding also separates keys on case-insensitive filesystems.
    chat_dir = hashlib.sha256(chat_key.encode('utf-8')).hexdigest()
    local = contained_path(gitdir, gitdir / 'pipeline-work' / version / chat_dir)
    return StatePaths(root, plans, local, gitdir, common, version, chat_key)


def legacy_source(paths: StatePaths, source: Path | str) -> Path:
    """Validate an explicitly requested legacy source before any session read.

    Checkout-local plans already prove the checkout; the caller must also match
    the recorded session parent. Shared common-dir sources need an identity
    sidecar in addition. No source in another checkout's plans is considered.
    """
    given = Path(os.path.abspath(source))
    if given == paths.plans / 'sessions.md':
        return contained_path(paths.checkout, given)
    old = contained_path(paths.common_dir, paths.common_dir / 'pipeline-work' / paths.version)
    given = contained_path(old, given)
    if given.name != 'sessions.md':
        raise ValueError('legacy source must be a sessions.md file')
    identity = contained_path(old, given.with_name('state-identity.json'))
    try:
        metadata = json.loads(identity.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise ValueError('legacy common-dir source has no valid checkout/chat identity') from exc
    expected = {'checkout': str(paths.checkout), 'version': paths.version, 'chat_key': paths.chat_key}
    if not isinstance(metadata, dict) or any(metadata.get(key) != value for key, value in expected.items()):
        raise ValueError('legacy common-dir checkout, version or chat identity does not match')
    return given
