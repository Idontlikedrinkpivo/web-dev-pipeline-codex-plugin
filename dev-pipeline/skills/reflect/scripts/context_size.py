"""Read this Codex chat's context, never a neighbour's.

context_size.py <project-dir> [--thread-id ID] [--limit TOKENS] [--json]
CODEX_THREAD_ID is used unless --thread-id is given. Without either, only a
single unambiguous main chat is accepted. Exit 0 below threshold, 2 checkpoint
needed, 3 unknown (never interpreted as an empty context). Read-only.
"""
from __future__ import annotations
import argparse
import json
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import sessions


def positive(value: str) -> int:
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError('must be positive')
    return number


def measure(cwd: str, thread_id: str | None, limit: int | None = None) -> dict:
    root = os.path.realpath(cwd)
    candidates = []
    for path in sessions.rollouts():
        meta = sessions.meta(path)
        if not meta or os.path.realpath(str(meta.get('cwd', ''))) != root:
            continue
        sid = str(meta.get('id') or '')
        if thread_id:
            if sid != thread_id:
                continue
        elif meta.get('parent_thread_id') or isinstance(meta.get('source'), dict) and 'subagent' in meta['source']:
            continue
        candidates.append((path, sid))
    ids = {sid for _, sid in candidates if sid}
    if not candidates or len(ids) != 1 or any(not sid for _, sid in candidates):
        return {'status': 'UNKNOWN', 'thread_id': thread_id, 'reason': 'chat not found or ambiguous; pass --thread-id'}
    latest = None
    last_compaction = ""
    for path, sid in candidates:
        for index, record in enumerate(sessions.records(path)):
            payload = record.get('payload') or {}
            if record.get('type') == 'compacted':
                last_compaction = max(last_compaction, record.get('timestamp') or '')
            if record.get('type') != 'event_msg' or payload.get('type') != 'token_count':
                continue
            info = payload.get('info') or {}
            usage = info.get('last_token_usage') or {}
            tokens = usage.get('input_tokens')
            if not isinstance(tokens, int) or isinstance(tokens, bool) or tokens <= 0:
                continue
            window = info.get('model_context_window')
            if not isinstance(window, int) or isinstance(window, bool) or window <= 0:
                window = None
            key = (record.get('timestamp') or '', index, str(path))
            if latest is None or key > latest[0]:
                latest = (key, tokens, window, sid)
    if latest is None or last_compaction and last_compaction >= latest[0][0]:
        return {'status': 'UNKNOWN', 'thread_id': next(iter(ids)), 'reason': 'no current token usage recorded'}
    _, tokens, window, sid = latest
    # Leave headroom to finish an item and save its checkpoint before host compaction.
    threshold = limit if limit is not None else min(300_000, window * 7 // 10) if window else 300_000
    return {'status': 'CHECKPOINT' if tokens >= threshold else 'OK', 'thread_id': sid,
            'input_tokens': tokens, 'model_context_window': window, 'limit': threshold}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project')
    parser.add_argument('--thread-id', default=os.environ.get('CODEX_THREAD_ID'))
    parser.add_argument('--limit', type=positive)
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    result = measure(args.project, args.thread_id, args.limit)
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    elif result['status'] == 'UNKNOWN':
        print('контекст: неизвестен — ' + result['reason'])
    else:
        print(f"контекст: {result['input_tokens'] // 1000} тыс. токенов · чат {result['thread_id']} · "
              f"порог {result['limit'] // 1000} тыс. · {result['status']}")
    sys.exit({'OK': 0, 'CHECKPOINT': 2, 'UNKNOWN': 3}[result['status']])


if __name__ == '__main__':
    main()
