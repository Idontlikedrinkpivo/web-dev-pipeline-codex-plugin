"""Stop hook: progress changed this turn needs an HTML link in the final response.

Reads the supplied transcript only, never executes its tool text. Native Codex
turn IDs take precedence over user-message boundaries; legacy JSONL is supported.
stop_hook_active bypasses the second consecutive Stop, including a bad Markdown
link, to prevent an infinite loop. A .md link is otherwise blocked even without
a progress edit or alongside an HTML link. Missing/unreadable evidence fails open.
"""
from __future__ import annotations

import json
import re
import shlex
import sys
from pathlib import Path

from guard import checkout_root, edit_chunks, is_progress

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/reflect/scripts"))
from sessions import literal_calls

TOOLS = {"apply_patch", "Edit", "Write", "MultiEdit", "Bash", "exec_command"}
SCRIPTS = {"progress_set.py", "progress_e2e.py"}
FILE = r"(?:progress[\w-]*|test-run|security-audit)"
LINK = re.compile(r"\[([^\]\n]+)\]\(\s*(<[^>\n]+>|[^)\n]+)\s*\)")


def current_turn(records: list[dict], turn_id: str | None) -> list[dict]:
    """Select a turn without mistaking in-turn steering/compaction for a new turn."""
    boundaries = []
    for i, row in enumerate(records):
        payload = row.get("payload") or {}
        if row.get("type") == "event_msg" and payload.get("type") == "task_started":
            identifier = payload.get("turn_id")
            if not boundaries or not identifier or boundaries[-1][1] != identifier:
                boundaries.append((i, identifier))
        elif row.get("type") == "turn_context" and payload.get("turn_id"):
            if not boundaries or boundaries[-1][1] != payload["turn_id"]:
                boundaries.append((i, payload["turn_id"]))
    if boundaries:
        matches = [i for i, (_, identifier) in enumerate(boundaries) if not turn_id or identifier == turn_id]
        if not matches:
            return []  # known history belongs to a different turn
        at = matches[-1]
        start = boundaries[at][0]
        end = boundaries[at + 1][0] if at + 1 < len(boundaries) else len(records)
        return records[start:end]
    start = 0
    for i, row in enumerate(records):
        payload = row.get("payload") or {}
        message = row.get("message") or {}
        if ((row.get("type") == "event_msg" and payload.get("type") == "user_message")
                or (row.get("type") == "response_item" and payload.get("role") == "user")
                or (row.get("type") == "user" and not any(
                    isinstance(part, dict) and part.get("type") == "tool_result"
                    for part in message.get("content", []) if isinstance(message.get("content"), list)))):
            start = i
    return records[start:]


def calls(row: dict):
    payload = row.get("payload") or {}
    if row.get("type") == "response_item" and payload.get("type") in ("function_call", "custom_tool_call"):
        name = re.split(r"__|\.", payload.get("name", ""))[-1]
        value = payload.get("arguments", payload.get("input", {}))
        if name == "exec":
            yield from literal_calls(str(value), TOOLS)
        elif name in TOOLS:
            if isinstance(value, str) and payload.get("type") == "function_call":
                try:
                    value = json.loads(value)
                except ValueError:
                    return
            yield name, value
    elif row.get("type") == "assistant":
        content = (row.get("message") or {}).get("content", [])
        for part in content if isinstance(content, list) else []:
            if isinstance(part, dict) and part.get("type") == "tool_use":
                yield part.get("name", ""), part.get("input", {})


def script_called(command: str) -> bool:
    def invokes(words: list[str]) -> bool:
        words = list(words)
        if words and words[0] in ("env", "command"):
            words.pop(0)
        while words and re.match(r"^[A-Za-z_]\w*=", words[0]):
            words.pop(0)
        if not words:
            return False
        if Path(words[0]).name in SCRIPTS:
            return True
        if not re.fullmatch(r"python(?:3(?:\.\d+)?)?", Path(words[0]).name):
            return False
        args = iter(words[1:])
        for arg in args:
            if arg in ("-c", "-m"):
                return False
            if arg in ("-X", "-W"):
                next(args, None)
            elif not arg.startswith("-"):
                return Path(arg).name in SCRIPTS
        return False

    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
        lexer.whitespace = " \t\r"  # a newline starts a new command too
        tokens = list(lexer)
    except ValueError:
        return False
    segment = []
    for token in tokens:
        if token in (";", "&&", "||", "|", "&", "(", ")", "\n"):
            if invokes(segment):
                return True
            segment = []
            continue
        segment.append(token)
    return invokes(segment)


def progress_changed(rows: list[dict], cwd: str) -> bool:
    for row in rows:
        for name, value in calls(row):
            if any(is_progress(path, cwd) for path, _, _ in edit_chunks(name, value)):
                return True
            if name in ("Bash", "exec_command") and isinstance(value, dict):
                if script_called(str(value.get("command") or value.get("cmd") or "")):
                    return True
    return False


def last_answer(rows: list[dict]) -> str:
    answer = ""
    for row in rows:
        payload = row.get("payload") or {}
        if row.get("type") == "event_msg" and payload.get("type") == "agent_message":
            answer = str(payload.get("message") or "")
        message = row.get("message") if row.get("type") == "assistant" else payload
        if isinstance(message, dict) and (row.get("type") == "assistant" or message.get("role") == "assistant"):
            content = message.get("content", [])
            text = content if isinstance(content, str) else "\n".join(
                str(p.get("text", "")) for p in content if isinstance(p, dict) and p.get("type") in ("text", "output_text"))
            if text:
                answer = text
    return answer


def decide(data: dict, records: list[dict]) -> str | None:
    if data.get("stop_hook_active") is True:
        return None
    rows = current_turn(records, data.get("turn_id"))
    answer = data.get("last_assistant_message")
    if not isinstance(answer, str):
        answer = last_answer(rows)
    # A link inside example code is not a clickable progress line.
    answer = re.sub(r"```[\s\S]*?```|`[^`\n]*`", "", answer)
    links = LINK.findall(answer)
    md_link = any(re.search(rf"(?:^|/){FILE}\.md(?:$|[?#])", label.strip()) or
                  re.search(rf"(?:^|/){FILE}\.md(?:$|[?#])", target.strip().strip("<>"))
                  for label, target in links)
    html_link = any(re.fullmatch(rf"{FILE}\.html", label.strip()) and
                    re.search(r"\.html(?:$|[?#])", target.strip().strip("<>")) for label, target in links)
    if md_link or (progress_changed(rows, str(data.get("cwd") or ".")) and not html_link):
        why = "Ссылка ведёт на Markdown прогресса." if md_link else "В этом ходе менялся прогресс, но в ответе нет ссылки на его страницу."
        return (f"dev-pipeline: {why} Запусти progress_link.py <файл прогресса .md> и вставь "
                "напечатанную строку со ссылкой [progress….html](…) (для UI — test-run.html, "
                "для аудита — security-audit.html). Ссылку на сам .md убери. Повторный Stop пропускается.")
    return None


def main() -> None:
    data = json.load(sys.stdin)
    if not isinstance(data, dict) or data.get("stop_hook_active") is True:
        return
    root = checkout_root(data.get("cwd") or ".")
    if not (root / "documentation/.dev-pipeline.json").is_file():
        return
    records = []
    try:
        with Path(data.get("transcript_path") or "").open(encoding="utf-8") as stream:
            for line in stream:
                try:
                    row = json.loads(line)
                    if isinstance(row, dict):
                        records.append(row)
                except ValueError:
                    continue
    except OSError:
        pass
    reason = decide(data, records)
    if reason:
        print(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, TypeError, AttributeError):
        pass  # missing or malformed host evidence must not trap the session
