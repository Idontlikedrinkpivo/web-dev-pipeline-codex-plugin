#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Print a saved stage's rules after compaction, using checkout/chat-owned state.

    python3 keep_rules.py [transcript.jsonl] --checkout ROOT --version V --thread-id ID

The durable stage comes from a complete local checkpoint's runtime.stage (a
canonical subsession stage key), or exact active subsession membership. Conflicts
fail safely to general recovery. Legacy positional transcripts supply a labeled
hint only, never authority. Missing logs do not break startup. Standard library only.
"""
from __future__ import annotations

import re
import argparse
import hashlib
import json
import os
import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from state_paths import contained_path, resolve_paths
from subsessions import STAGES, owner_of, read

REF = Path(__file__).resolve().parent.parent / "references" / "keep-after-compaction.md"
SKILL = re.compile(r'"skill"\s*:\s*"dev-pipeline:([a-z][\w-]*)"|\$dev-pipeline:([a-z][\w-]*)'
                   r'|Base directory for this skill: [^"\n]*?/([a-z][\w-]*)(?=[\\"\n])|/skills/([a-z][\w-]*)/SKILL\.md')


def sections(text: str) -> dict[str, str]:
    out, name, body = {}, None, []
    for line in text.splitlines():
        m = re.match(r"^## ([\w-]+)\s*$", line)
        if m:
            if name:
                out[name] = "\n".join(body).strip()
            name, body = m.group(1), []
        elif name:
            body.append(line)
    if name:
        out[name] = "\n".join(body).strip()
    return out


def saved_stage(checkout: str, version: str, thread: str) -> str | None:
    """Only identity-proven local evidence may choose the stage, never skill reads."""
    paths = resolve_paths(checkout, version, thread)
    candidates = []
    pointer = contained_path(paths.checkout, paths.plans / 'run-state.json')
    if pointer.exists():
        state = json.loads(pointer.read_text(encoding='utf-8'))
        checkpoint_id = state.get('checkpoint_id', '')
        if state.get('schema_version') != 1 or state.get('version') != version or not re.fullmatch(r'[0-9a-f]{32}', checkpoint_id):
            raise ValueError('unknown checkpoint schema or iteration')
        folder = contained_path(paths.gitdir, paths.local / 'checkpoints' / checkpoint_id)
        manifest = json.loads(contained_path(paths.gitdir, folder / 'manifest.json').read_text(encoding='utf-8'))
        identity = {'checkout': str(paths.checkout), 'gitdir': str(paths.gitdir),
                    'chat_key': thread, 'host': socket.gethostname()}
        if (manifest.get('local_identity') != identity or manifest.get('checkpoint_id') != checkpoint_id
                or manifest.get('schema_version') != 1 or manifest.get('version') != version
                or manifest.get('completeness', {}).get('scope') != 'local'
                or manifest.get('completeness', {}).get('local') is not True
                or manifest.get('paused') is not False):
            raise ValueError('checkpoint identity/completeness does not match this active chat')
        runtime_bytes = contained_path(paths.gitdir, folder / 'runtime.json').read_bytes()
        if hashlib.sha256(runtime_bytes).hexdigest() != manifest.get('payload', {}).get('runtime.json'):
            raise ValueError('runtime checksum mismatch')
        runtime = json.loads(runtime_bytes)
        if runtime.get('identity') != identity:
            raise ValueError('runtime identity mismatch')
        stage = runtime.get('runtime', {}).get('stage')
        if stage is not None:
            candidates.append(stage)
    parent, rows = read(contained_path(paths.gitdir, paths.local / 'sessions.md'))
    if parent not in ('', '—', thread):
        raise ValueError('registry identity mismatch')
    hits = [row for row in rows if row.get('id') == thread and row.get('state') == 'идёт']
    owner = owner_of(paths, thread)
    if owner is not None and owner[1].get('state') == 'идёт':
        hits.append(owner[1])
    if len(hits) > 1:
        raise ValueError('ambiguous active session')
    candidates.extend(row['stage'] for row in hits)
    if any(stage not in STAGES for stage in candidates) or len(set(candidates)) > 1:
        raise ValueError('unknown or contradictory active stage')
    return STAGES[candidates[0]][1].split()[0] if candidates else None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('transcript', nargs='?')
    parser.add_argument('--checkout', default=os.environ.get('PWD', '.'))
    parser.add_argument('--version')
    parser.add_argument('--thread-id', default=os.environ.get('CODEX_THREAD_ID', ''))
    args = parser.parse_args()
    known = sections(REF.read_text(encoding='utf-8'))
    stage, reason = None, 'missing durable checkout/chat/iteration state'
    if args.version and args.thread_id:
        try:
            stage = saved_stage(args.checkout, args.version, args.thread_id)
        except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
            reason = str(exc)
    if stage not in known:
        print('dev-pipeline: stage recovery required — ' + reason + '; verify saved state before continuing.')
        stage = 'pipeline'
        if args.transcript:
            try:
                text = Path(args.transcript).read_text(encoding='utf-8', errors='replace')
                names = [next(g for g in m.groups() if g) for m in SKILL.finditer(text)]
                hint = next((n for n in reversed(names) if n in known), None)
                if hint:
                    print('Legacy transcript hint only (not active stage): ' + hint)
            except OSError:
                print('Legacy transcript unavailable.')
    print(f'dev-pipeline: not to lose in this stage ({stage}, pipeline → references/keep-after-compaction.md):')
    print(known.get(stage, 'Read pipeline and recover the saved stage.'))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError) as exc:
        print(f'dev-pipeline: stage recovery required — {exc}')
