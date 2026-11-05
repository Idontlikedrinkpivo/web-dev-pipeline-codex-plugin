#!/usr/bin/env python3
"""Find this project's Codex sessions and boil each down to a readable digest for `reflect`.

usage:
  sessions.py list   <project-dir> [--since YYYY-MM-DD[THH:MM]] [--also <old-project-dir> ...]
                     one line per session: path, start, end, size; a session whose typed messages
                     all reappear, in order, at the start of a longer one (it was resumed into a new
                     file) is marked «# повтор <id>» and skipped
  sessions.py digest <rollout.jsonl[.zst]> <out.md>          the session as a short chronological digest
  sessions.py mine   <project-dir> <marker> <out.md>   the digest of the newest session of this folder whose first
                     message holds the marker — a nested chat's title: its own conversation, for the check before
                     its stage closes
  sessions.py errors <project-dir> <out.md> [--since …] [--also …]   failed calls of the sessions and the agents they
                     spawned, grouped. Codex writes a call's output as plain text and keeps no success flag in the
                     rollout, so a failure is read from the text: «Exit code: N» not 0, a timeout, an error line

The Codex build of the plugin ships this file in place of the Claude Code one. Codex keeps each session as a
rollout file: ${CODEX_HOME:-~/.codex}/sessions/YYYY/MM/DD/rollout-<time>-<id>.jsonl (older ones may be
compressed to .jsonl.zst, read through the `zstd` command; archived ones sit in archived_sessions/). Each line
is {"timestamp", "type", "payload"}; the session_meta line names the folder the session ran in, and only
sessions of this project's folder are read — never another project's. Sessions of spawned agents are skipped:
the main session already shows what each spawn returned.
"""
from __future__ import annotations
import json, os, re, shutil, subprocess, sys
import ast
import bz2
import gzip
import html
import lzma
from pathlib import Path

HOME = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
CONTINUATION_KEYS = ("resumed_from_id", "resumed_from", "continuation_of", "continued_from", "forked_from_id")


def _lineage_problem(value: object, field: str) -> str | None:
    if value is None or isinstance(value, str):
        return None
    if not isinstance(value, dict):
        return f"{field} (expected string or object)"
    for key in ("thread_id", "session_id", "id"):
        identifier = value.get(key)
        if identifier is not None and not isinstance(identifier, str):
            return f"{field}.{key} (expected string)"
    return None


def _metadata_problem(payload: dict) -> str | None:
    """Validate fields consumed by scope/classification before exposing metadata."""
    nodes = [("", payload)]
    source = payload.get("source")
    if source is not None and not isinstance(source, (str, dict)):
        return "source (expected string or object)"
    if isinstance(source, dict):
        for key in ("resume", "continuation"):
            problem = _lineage_problem(source.get(key), f"source.{key}")
            if problem:
                return problem
        for key in ("subagent", "sub_agent"):
            sub = source.get(key)
            if sub is not None and not isinstance(sub, (str, dict)):
                return f"source.{key} (expected string or object)"
            if isinstance(sub, dict):
                nodes.append((f"source.{key}.", sub))
                spawn = sub.get("thread_spawn")
                if spawn is not None and not isinstance(spawn, dict):
                    return f"source.{key}.thread_spawn (expected object)"
                if isinstance(spawn, dict):
                    nodes.append((f"source.{key}.thread_spawn.", spawn))
    for prefix, node in nodes:
        for key in ("id", "cwd", "parent_thread_id", "parent_session_id", "agent_role", "agent_type", "agent_nickname"):
            value = node.get(key)
            if value is not None and not isinstance(value, str):
                return f"{prefix}{key} (expected string)"
    for key in CONTINUATION_KEYS:
        problem = _lineage_problem(payload.get(key), key)
        if problem:
            return problem
    return None


def incomplete(path: Path, reason: str, diagnostics: list | None = None, line: int | None = None) -> None:
    item = {"path": str(path), "reason": reason, "line": line}
    if diagnostics is not None:
        diagnostics.append(item)
    print(f"incomplete: {path}" + (f":{line}" if line else "") + f": {reason}", file=sys.stderr)


def lines(path: Path, diagnostics: list | None = None):
    if path.suffix == ".zst":
        if not shutil.which("zstd"):
            incomplete(path, "compressed, no zstd command", diagnostics)
            return
        try:
            out = subprocess.run(["zstd", "-dc", str(path)], capture_output=True, text=True, errors="replace")
            if out.returncode:
                incomplete(path, "zstd decompression failed", diagnostics)
            yield from out.stdout.splitlines()
        except OSError as exc:
            incomplete(path, f"zstd unavailable: {exc}", diagnostics)
    else:
        opener = {".gz": gzip.open, ".bz2": bz2.open, ".xz": lzma.open}.get(path.suffix, open)
        try:
            with opener(path, "rt", encoding="utf-8") as fh:
                yield from fh
        except (OSError, EOFError, UnicodeError, lzma.LZMAError) as exc:
            incomplete(path, f"cannot read/decompress: {exc}", diagnostics)


def records(path: Path, diagnostics: list | None = None):
    for number, line in enumerate(lines(path, diagnostics), 1):
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            incomplete(path, "invalid JSON record", diagnostics, number)
            continue
        if isinstance(d, dict):
            yield d
        else:
            incomplete(path, "invalid record (expected object)", diagnostics, number)


def rollouts(diagnostics: list | None = None) -> list[Path]:
    if not HOME.is_dir():
        incomplete(HOME, "CODEX_HOME is absent", diagnostics)
        return []
    found = []
    for sub in ("sessions", "archived_sessions"):
        root = HOME / sub
        if root.is_dir():
            found += [p for p in root.rglob("rollout-*") if p.is_file() and p.name.endswith(
                (".jsonl", ".jsonl.zst", ".jsonl.gz", ".jsonl.bz2", ".jsonl.xz"))]
    if not found:
        incomplete(HOME, "no rollout sources in sessions/archived_sessions", diagnostics)
    return sorted(set(found))


def meta(path: Path, diagnostics: list | None = None) -> dict:
    for d in records(path, diagnostics):
        if d.get("type") == "session_meta":
            payload = d.get("payload")
            if not isinstance(payload, dict):
                incomplete(path, "invalid session_meta payload (expected object)", diagnostics)
                return {}
            problem = _metadata_problem(payload)
            if problem:
                incomplete(path, f"invalid session_meta {problem}", diagnostics)
                return {}
            return payload
    return {}


def text_of(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b["text"] for b in content if isinstance(b, dict)
                         and b.get("type", "text") in ("text", "input_text", "output_text")
                         and isinstance(b.get("text"), str))
    return ""


def normalized_records(path: Path, diagnostics: list | None = None):
    """Canonical messages plus unchanged non-message records, in source order.

    Pair only complementary encodings in an uninterrupted run of equal messages.
    Turn boundaries and different messages close the run; same-encoding repeats
    always remain separate. Provenance retains every paired source record.
    """
    out, pending = [], []
    previous = None
    for index, d in enumerate(records(path, diagnostics)):
        payload = d.get("payload")
        p = payload if isinstance(payload, dict) else {}
        kind, role, text = d.get("type"), None, ""
        if kind == "event_msg" and p.get("type") in ("user_message", "agent_message"):
            role = "user" if p["type"] == "user_message" else "assistant"
            text = text_of(p.get("message")).strip()
        elif kind == "response_item" and p.get("type") == "message" and p.get("role") in ("user", "assistant"):
            role, text = p["role"], text_of(p.get("content")).strip()
        if role and text:
            key = (role, text, p.get("turn_id"))
            if key != previous:
                pending = []
            previous = key
            provenance = {"path": str(path), "index": index, "encoding": kind, "timestamp": d.get("timestamp", "")}
            pair = next((m for m in pending if len(m["payload"]["provenance"]) == 1
                         and m["payload"]["provenance"][0]["encoding"] != kind), None)
            if pair is not None:
                pair["payload"]["provenance"].append(provenance)
                pending.remove(pair)
            else:
                canonical = {"type": "message", "timestamp": d.get("timestamp", ""),
                             "payload": {"role": role, "text": text, "provenance": [provenance]}}
                pending.append(canonical)
                out.append(canonical)
        else:
            # Tools may sit between the two representations of a final message.
            if kind in ("turn_context", "compacted") or (kind == "event_msg" and p.get("type") in (
                    "task_started", "task_complete", "turn_started", "turn_complete", "context_compacted")):
                pending, previous = [], None
            out.append(d)
    yield from out


def messages(path: Path, diagnostics: list | None = None) -> list[dict]:
    return [{**d["payload"], "timestamp": d.get("timestamp", "")} for d in normalized_records(path, diagnostics)
            if d.get("type") == "message"]


def typed(path: Path) -> list[str]:
    return [m["text"][:200] for m in messages(path) if m["role"] == "user"]


def roots_of(cwd: str, also: list) -> list[str]:
    roots = {os.path.realpath(x) for x in [cwd] + list(also)}
    for root in list(roots):
        try:
            result = subprocess.run(["git", "-C", root, "worktree", "list", "--porcelain"],
                                    capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                roots.update(os.path.realpath(line[9:]) for line in result.stdout.splitlines()
                             if line.startswith("worktree "))
        except (OSError, subprocess.TimeoutExpired):
            continue  # an explicit directory is still a valid root outside git
    return sorted(roots)


def spawn_of(m: dict) -> dict:
    source = m.get("source")
    if isinstance(source, dict):
        sub = source.get("subagent") or source.get("sub_agent")
        if isinstance(sub, dict):
            spawn = sub.get("thread_spawn")
            return spawn if isinstance(spawn, dict) else sub
    return {}


def parent_of(m: dict) -> str | None:
    spawn = spawn_of(m)
    return m.get("parent_thread_id") or m.get("parent_session_id") or spawn.get("parent_thread_id") or spawn.get("parent_session_id")


def role_of(m: dict) -> str | None:
    spawn = spawn_of(m)
    role = m.get("agent_role") or m.get("agent_type") or spawn.get("agent_role") or spawn.get("agent_type")
    source = m.get("source")
    subagent = isinstance(source, dict) and any(k in source for k in ("subagent", "sub_agent"))
    if not parent_of(m) and not role and not subagent and source not in ("subagent", "sub_agent"):
        return None
    return role or m.get("agent_nickname") or spawn.get("agent_nickname") or "агент"


def continuation_of(m: dict) -> str | None:
    for key in CONTINUATION_KEYS:
        value = m.get(key)
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            return value.get("thread_id") or value.get("session_id") or value.get("id")
    source = m.get("source")
    if isinstance(source, dict):
        for key in ("resume", "continuation"):
            value = source.get(key)
            if isinstance(value, str):
                return value
            if isinstance(value, dict):
                return value.get("thread_id") or value.get("session_id") or value.get("id")
    return None


def project_rollouts(cwd: str, also: list | None = None, *, include_agents: bool = True,
                     diagnostics: list | None = None) -> list[tuple[Path, dict]]:
    """One project scope for list/mine/errors/measure, including known lineage."""
    roots = roots_of(cwd, also or [])
    candidates = [(p, meta(p, diagnostics)) for p in rollouts(diagnostics)]
    selected, ids = [], set()
    while candidates:
        remaining = []
        for path, m in candidates:
            where = os.path.realpath(m["cwd"]) if isinstance(m.get("cwd"), str) and m["cwd"] else ""
            matches = any(where == r or where.startswith(r + os.sep) for r in roots)
            inherited = not where and (parent_of(m) in ids or continuation_of(m) in ids)
            if m and (matches or inherited):
                selected.append((path, m))
                if m.get("id"):
                    ids.add(m["id"])
            else:
                remaining.append((path, m))
        if len(remaining) == len(candidates):
            break
        candidates = remaining
    return sorted(((p, m) for p, m in selected if include_agents or role_of(m) is None),
                  key=lambda item: (item[0].stat().st_mtime, str(item[0])))


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
    sources = project_rollouts(cwd, also, include_agents=False)
    metadata = {p: m for p, m in sources}
    by_id = {m.get("id"): m for _, m in sources if m.get("id")}

    def continues(new: dict, old: dict) -> bool:
        target, seen = old.get("id"), set()
        if not target:
            return False
        while new:
            if new.get("id") == target:
                return True
            parent = continuation_of(new)
            if parent == target:
                return True
            if not parent or parent in seen:
                break
            seen.add(parent)
            new = by_id.get(parent, {})
        return False

    rows = []
    for p, _ in sources:
        a, b = span(p)
        if since and b and b[:len(since)] < since:  # a date, or a date and time (2026-10-09T12:10)
            continue
        rows.append((p, a, b, typed(p)))
    if not rows:
        print(f"no sessions of {cwd} in {HOME}/sessions", file=sys.stderr)
        sys.exit(1)
    for p, a, b, msgs in rows:
        dup = next((q for q, _, _, m in rows if q != p and msgs and len(m) > len(msgs)
                    and m[:len(msgs)] == msgs and continues(metadata[q], metadata[p])), None)
        if dup:
            print(f"# повтор {sid(dup)}: {p}")
            continue
        print(f"{p}\t{a}\t{b}\t{p.stat().st_size // 1024} KB")


def cmd_mine(cwd: str, marker: str, out: str, also: list[str] | None = None) -> None:
    for p, _ in reversed(project_rollouts(cwd, also, include_agents=False)):
        first = next((m["text"] for m in messages(p) if m["role"] == "user"), "")
        if marker in first:
            cmd_digest(str(p), out)
            return
    print(f"no session of {cwd} opens with «{marker}»", file=sys.stderr)
    sys.exit(1)


def skill_read(args: str) -> str:
    """The skill a shell call opened, when the call reads a SKILL.md of the plugin."""
    marker = "/skills/"
    i = args.find(marker)
    if i < 0 or "SKILL.md" not in args[i:]:
        return ""
    return args[i + len(marker):].split("/", 1)[0]


CHAT_TOOLS = {
    "create_thread": "open", "start_session": "open", "create_session": "open",
    "send_message_to_thread": "send", "send_message": "send",
    "set_thread_title": "rename", "rename_thread": "rename", "set_session_title": "rename",
    "set_thread_archived": "archive", "archive_thread": "archive", "archive_session": "archive",
}


def tool_action(name: str) -> str:
    # MCP namespaces differ between installations; match the final tool component only.
    return CHAT_TOOLS.get(re.split(r"__|\.", name)[-1], "")


def literal_calls(code: str):
    """Read literal tools.foo({...}) calls in code-mode exec; never evaluate rollout JavaScript.

    Tokenizing strings first avoids treating example code inside a shell command as a call.
    Dynamic arguments are deliberately skipped rather than guessed.
    """
    tokens = re.findall(r'''//[^\n]*|/\*[\s\S]*?\*/|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`|[A-Za-z_$][\w$]*|-?\d+(?:\.\d+)?|[^\s]''', code)
    tokens = [t for t in tokens if not t.startswith(("//", "/*"))]

    def value(i):
        t = tokens[i]
        if t == "{":
            obj = {}; i += 1
            while tokens[i] != "}":
                key = tokens[i]
                if key[:1] in ('"', "'"):
                    key = ast.literal_eval(key)
                elif not re.fullmatch(r"[A-Za-z_$][\w$]*", key):
                    raise ValueError("dynamic key")
                if tokens[i + 1] != ":":
                    raise ValueError("dynamic property")
                obj[key], i = value(i + 2)
                if tokens[i] != ",":
                    break
                i += 1
            if tokens[i] != "}":
                raise ValueError("unclosed object")
            return obj, i + 1
        if t == "[":
            items = []; i += 1
            while tokens[i] != "]":
                item, i = value(i); items.append(item)
                if tokens[i] != ",":
                    break
                i += 1
            if tokens[i] != "]":
                raise ValueError("unclosed array")
            return items, i + 1
        if t.startswith('"'):
            return json.loads(t), i + 1
        if t.startswith("'"):
            return ast.literal_eval(t), i + 1
        if t.startswith("`") and "${" not in t:
            return t[1:-1], i + 1
        if t in ("true", "false", "null") or re.fullmatch(r"-?\d+(?:\.\d+)?", t):
            return json.loads(t), i + 1
        raise ValueError("dynamic argument")

    for i in range(len(tokens) - 4):
        if tokens[i:i + 2] != ["tools", "."] or tokens[i + 3] != "(":
            continue
        name = tokens[i + 2]
        if not tool_action(name):
            continue
        try:
            args, end = value(i + 4)
            if isinstance(args, dict) and tokens[end] == ")":
                yield name, args
        except (ValueError, SyntaxError, IndexError):
            continue


def chat_call(name: str, args: dict) -> str:
    action = tool_action(name)
    target = args.get("threadId") or args.get("thread_id") or args.get("session_id") or args.get("sessionId") or "?"
    title = args.get("title") or args.get("name") or "?"
    message = str(args.get("prompt") or args.get("message") or "")[:2000]
    if action == "open" and message:
        return f"OPENS SESSION «{title}» ({args.get('model') or 'default'}): {message}"
    if action == "send" and target != "?":
        return f"TO SESSION {target}: {message}"
    if action == "rename" and target != "?":
        return f"RENAMES: {target} → «{title}»"
    if action == "archive" and target != "?":
        return f"ARCHIVES: {target}" + (" (archived=false)" if args.get("archived") is False else "")
    return ""


def delegation(payload: dict) -> str:
    """Codex app injects cross-chat prompts as tool output, not USER messages.

    Match the envelope only at the start: quoted examples and tool-result logs
    containing an envelope are not incoming messages.
    """
    output = payload.get("output")
    if not isinstance(output, str) or not output.lstrip().startswith("<codex_delegation>"):
        return ""
    def field(key):
        m = re.search(rf"<{key}>([\s\S]*?)</{key}>", output)
        return html.unescape(m.group(1).strip()) if m else ""
    message = field("input")
    if not message:
        return ""
    if tool_action(payload.get("name") or "") == "open":
        return f"OPENED BY SESSION: {message[:2000]}"
    if tool_action(payload.get("name") or "") == "send":
        title = (field("source_thread_title") or field("source_session_title")
                 or field("source_thread_name") or field("source_thread_id") or "?")
        return f"FROM SESSION «{title}»: {message[:2000]}"
    return ""


def cmd_digest(src: str, out: str, since: str | None = None) -> None:
    rows: list[str] = []
    since = since.replace("T", " ") if since else None
    for d in normalized_records(Path(src)):
        ts = (d.get("timestamp") or "")[:16].replace("T", " ")
        if since and ts and ts < since:  # read by an earlier reflect section
            continue
        t, p = d.get("type"), d.get("payload") or {}
        if t == "message":
            label, limit = ("USER", 2000) if p["role"] == "user" else ("CODEX", 700)
            rows.append(f"[{ts}] {label}: {p['text'][:limit]}")
        elif t == "event_msg":
            kind = p.get("type")
            if kind == "context_compacted":
                rows.append(f"[{ts}] === CONTEXT COMPACTED ===")
        elif t == "compacted":
            rows.append(f"[{ts}] === CONTEXT COMPACTED ===")
        elif t == "response_item" and p.get("type") in ("function_call_output", "custom_tool_call_output"):
            incoming = delegation(p)
            if incoming:
                rows.append(f"[{ts}] {incoming}")
        elif t == "response_item" and p.get("type") in ("function_call", "custom_tool_call"):
            name, args = p.get("name") or "", p.get("arguments") or p.get("input") or ""
            try:
                a = json.loads(args) if isinstance(args, str) else args
                a = a if isinstance(a, dict) else {}
            except ValueError:
                a = {}
            call = chat_call(name, a)
            if call:
                rows.append(f"[{ts}] {call}")
            elif name in ("exec", "functions.exec"):
                for nested_name, nested_args in literal_calls(str(args)):
                    rows.append(f"[{ts}] {chat_call(nested_name, nested_args)}")
            if name == "spawn_agent":
                who = a.get("agent_type") or a.get("agent") or a.get("name") or a.get("task_name") or "agent"
                rows.append(f"[{ts}] AGENT: {who} — {str(a.get('message', ''))[:120]}")
            else:
                skill = skill_read(args if isinstance(args, str) else json.dumps(args))
                if skill:
                    rows.append(f"[{ts}] SKILL: {skill}")
    # a skill read twice in a row (the file paged in parts) is one mention
    rows = [r for i, r in enumerate(rows) if not (r.split("] ", 1)[1].startswith("SKILL:")
                                                  and i and rows[i - 1].split("] ", 1)[1] == r.split("] ", 1)[1])]
    Path(out).write_text("\n".join(rows) + "\n")
    print(f"{out}: {len(rows)} entries")


def failed(out) -> str:
    """The error text of a failed call's output, or "" when it succeeded."""
    s = out if isinstance(out, str) else json.dumps(out, ensure_ascii=False)
    try:
        d = json.loads(s)
        code = (d.get("metadata") or {}).get("exit_code")
        if code not in (None, 0):
            return str(d.get("output", ""))[:600] or f"exit code {code}"
        return ""
    except (ValueError, AttributeError):
        pass
    # an exec call's text: "Exit code: N\nWall time: … seconds\nOutput:\n…" (codex-rs core/src/tools,
    # format_exec_output_for_model); a timeout starts "command timed out after N milliseconds"
    m = re.match(r"\s*(?:Exit code|Process exited with code):?\s*(\d+)", s)
    if m and m.group(1) != "0":
        return s[:600]
    return s[:600] if re.match(r"\s*(error|failed|unknown|no such|command timed out|apply_patch verification failed)",
                               s, re.I) else ""


def cmd_errors(cwd: str, out: str, since: str | None, also: list[str]) -> None:
    """The failed calls of this project's sessions and of the agents they spawned, grouped (no model reads them)."""
    groups: dict = {}
    total = 0
    for path, m in project_rollouts(cwd, also):
        who = "агент" if role_of(m) is not None else "сессия"
        calls: dict = {}
        for d in records(path):
            ts = (d.get("timestamp") or "")[:16]
            if since and ts and ts < since:
                continue
            p = d.get("payload") or {}
            if d.get("type") != "response_item":
                continue
            if p.get("type") in ("function_call", "custom_tool_call"):  # custom: apply_patch and the like
                calls[p.get("call_id")] = (p.get("name") or "", str(p.get("arguments") or p.get("input") or "")[:300])
            elif p.get("type") in ("function_call_output", "custom_tool_call_output"):
                err = failed(p.get("output"))
                if not err:
                    continue
                total += 1
                name, args = calls.get(p.get("call_id"), ("?", ""))
                first = next((l for l in err.splitlines() if l.strip() and not re.match(
                    r"(Exit code|Wall time|Output:|Total output lines)", l)), err[:100])[:140]
                key = (name, re.sub(r"\d+", "N", re.sub(r"/[^\s'\"]+", "<путь>", first)))
                g = groups.setdefault(key, {"n": 0, "who": set(), "ex": (args, err, ts)})
                g["n"] += 1
                g["who"].add(who)
    lines = [f"# Ошибки вызовов · {Path(cwd).name}" + (f" · с {since}" if since else ""), "",
             f"Вызовов с ошибкой: {total} · групп: {len(groups)} (журналы Codex; упавшие тесты и линтеры — дело кода)", ""]
    for (name, _), g in sorted(groups.items(), key=lambda kv: -kv[1]["n"])[:80]:
        args, err, ts = g["ex"]
        lines += [f"## ×{g['n']} · ошибка команды · {name}", f"- кто: {', '.join(sorted(g['who']))}",
                  f"- пример ({ts.replace('T', ' ')}): `{args[:240]}`", "- ошибка: " + re.sub(r"\s+", " ", err)[:400], ""]
    Path(out).write_text("\n".join(lines) + "\n")
    print(f"{out}: {total} failed calls in {len(groups)} groups")


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "list":
        since = sys.argv[sys.argv.index("--since") + 1] if "--since" in sys.argv else None
        also = [sys.argv[i + 1] for i, x in enumerate(sys.argv) if x == "--also"]
        cmd_list(sys.argv[2], since, also)
    elif len(sys.argv) >= 4 and sys.argv[1] == "digest":
        cmd_digest(sys.argv[2], sys.argv[3], sys.argv[sys.argv.index("--since") + 1] if "--since" in sys.argv else None)
    elif len(sys.argv) >= 5 and sys.argv[1] == "mine":
        cmd_mine(sys.argv[2], sys.argv[3], sys.argv[4],
                 [sys.argv[i + 1] for i, x in enumerate(sys.argv) if x == "--also"])
    elif len(sys.argv) >= 4 and sys.argv[1] == "errors":
        since = sys.argv[sys.argv.index("--since") + 1] if "--since" in sys.argv else None
        also = [sys.argv[i + 1] for i, x in enumerate(sys.argv) if x == "--also"]
        cmd_errors(sys.argv[2], sys.argv[3], since, also)
    else:
        print(__doc__)
        sys.exit(2)
