#!/usr/bin/env python3
"""Find this project's Codex sessions and boil each down to a readable digest for `reflect`.

usage:
  sessions.py list   <project-dir> [--since YYYY-MM-DD[THH:MM]] [--also <old-project-dir> ...]
                     one line per session: path, start, end, size; a session whose typed messages
                     all reappear, in order, at the start of a longer one (it was resumed into a new
                     file) is marked «# повтор <id>» and skipped
  sessions.py digest <rollout.jsonl[.zst]> <out.md>          the session as a short chronological digest

The Codex build of the plugin ships this file in place of the Claude Code one. Codex keeps each session as a
rollout file: ${CODEX_HOME:-~/.codex}/sessions/YYYY/MM/DD/rollout-<time>-<id>.jsonl (older ones may be
compressed to .jsonl.zst, read through the `zstd` command; archived ones sit in archived_sessions/). Each line
is {"timestamp", "type", "payload"}; the session_meta line names the folder the session ran in, and only
sessions of this project's folder are read — never another project's. Sessions of spawned agents are skipped:
the main session already shows what each spawn returned.
"""
from __future__ import annotations
import json, os, re, shutil, subprocess, sys
from pathlib import Path

HOME = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))


def lines(path: Path):
    if path.suffix == ".zst":
        if not shutil.which("zstd"):
            print(f"skipped (compressed, no zstd command): {path}", file=sys.stderr)
            return
        out = subprocess.run(["zstd", "-dc", str(path)], capture_output=True, text=True, errors="ignore")
        yield from out.stdout.splitlines()
        return
    with open(path, errors="ignore") as fh:
        yield from fh


def records(path: Path):
    for line in lines(path):
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(d, dict):
            yield d


def rollouts() -> list[Path]:
    found = []
    for sub in ("sessions", "archived_sessions"):
        root = HOME / sub
        if root.is_dir():
            found += [p for p in root.rglob("rollout-*") if p.name.endswith((".jsonl", ".jsonl.zst"))]
    return found


def meta(path: Path) -> dict:
    for d in records(path):
        if d.get("type") == "session_meta":
            return d.get("payload") or {}
    return {}


def text_of(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b.get("text", "") for b in content if isinstance(b, dict))
    return ""


def typed(path: Path) -> list[str]:
    out = []
    for d in records(path):
        p = d.get("payload") or {}
        if d.get("type") == "event_msg" and p.get("type") == "user_message":
            txt = (p.get("message") or "").strip()
            if txt:
                out.append(txt[:200])
    return out


def span(path: Path) -> tuple[str, str]:
    first = last = ""
    for d in records(path):
        ts = d.get("timestamp") or ""
        if ts:
            first = first or ts
            last = ts
    return first[:16], last[:16]


def sid(path: Path) -> str:
    """The short id of a rollout: the first 8 characters of the session id in its name."""
    m = re.search(r"([0-9a-f]{8})-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", path.name)
    return m.group(1) if m else path.name[:8]


def cmd_list(cwd: str, since: str | None, also: list[str]) -> None:
    roots = {os.path.realpath(x) for x in [cwd] + also}
    rows = []
    for p in sorted(rollouts(), key=lambda p: p.stat().st_mtime):
        m = meta(p)
        if not m or m.get("parent_thread_id") or os.path.realpath(str(m.get("cwd", ""))) not in roots:
            continue
        a, b = span(p)
        if since and b and b[:len(since)] < since:  # a date, or a date and time (2026-10-09T12:10)
            continue
        rows.append((p, a, b, typed(p)))
    if not rows:
        print(f"no sessions of {cwd} in {HOME}/sessions", file=sys.stderr)
        sys.exit(1)
    for p, a, b, msgs in rows:
        dup = next((q for q, _, _, m in rows if q != p and msgs and len(m) > len(msgs) and m[:len(msgs)] == msgs), None)
        if dup:
            print(f"# повтор {sid(dup)}: {p}")
            continue
        print(f"{p}\t{a}\t{b}\t{p.stat().st_size // 1024} KB")


def skill_read(args: str) -> str:
    """The skill a shell call opened, when the call reads a SKILL.md of the plugin."""
    marker = "/skills/"
    i = args.find(marker)
    if i < 0 or "SKILL.md" not in args[i:]:
        return ""
    return args[i + len(marker):].split("/", 1)[0]


def cmd_digest(src: str, out: str) -> None:
    rows: list[str] = []
    for d in records(Path(src)):
        ts = (d.get("timestamp") or "")[:16].replace("T", " ")
        t, p = d.get("type"), d.get("payload") or {}
        if t == "event_msg":
            kind = p.get("type")
            if kind == "user_message" and (p.get("message") or "").strip():
                rows.append(f"[{ts}] USER: {p['message'].strip()[:2000]}")
            elif kind == "agent_message" and (p.get("message") or "").strip():
                rows.append(f"[{ts}] CODEX: {p['message'].strip()[:700]}")
            elif kind == "context_compacted":
                rows.append(f"[{ts}] === CONTEXT COMPACTED ===")
        elif t == "compacted":
            rows.append(f"[{ts}] === CONTEXT COMPACTED ===")
        elif t == "response_item" and p.get("type") == "function_call":
            name, args = p.get("name") or "", p.get("arguments") or ""
            if name == "spawn_agent":
                try:
                    a = json.loads(args)
                except json.JSONDecodeError:
                    a = {}
                who = a.get("agent_type") or a.get("agent") or a.get("name") or a.get("task_name") or "agent"
                rows.append(f"[{ts}] AGENT: {who} — {str(a.get('message', ''))[:120]}")
            else:
                skill = skill_read(args)
                if skill:
                    rows.append(f"[{ts}] SKILL: {skill}")
    # a skill read twice in a row (the file paged in parts) is one mention
    rows = [r for i, r in enumerate(rows) if not (r.split("] ", 1)[1].startswith("SKILL:")
                                                  and i and rows[i - 1].split("] ", 1)[1] == r.split("] ", 1)[1])]
    Path(out).write_text("\n".join(rows) + "\n")
    print(f"{out}: {len(rows)} entries")


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "list":
        since = sys.argv[sys.argv.index("--since") + 1] if "--since" in sys.argv else None
        also = [sys.argv[i + 1] for i, x in enumerate(sys.argv) if x == "--also"]
        cmd_list(sys.argv[2], since, also)
    elif len(sys.argv) == 4 and sys.argv[1] == "digest":
        cmd_digest(sys.argv[2], sys.argv[3])
    else:
        print(__doc__)
        sys.exit(2)
