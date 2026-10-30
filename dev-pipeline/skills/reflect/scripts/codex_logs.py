"""Codex rollouts for reflect's measure.py — shipped in the Codex build as scripts/codex_logs.py.

measure.py imports this module when it sits beside it and takes the spend from Codex's own session files instead
of Claude Code's logs; the report (groups, agents, models, «Принятие задач», --json, compare.py) stays the same.

What Codex writes (codex-rs/protocol, protocol.rs): each rollout's first line is session_meta — its `cwd`, and for a
spawned agent `parent_thread_id` and `agent_role` (alias `agent_type`: impl-medium, review-hard, …) or
`source.subagent.thread_spawn` with the same fields. Each model response is followed by an event_msg `token_count`
whose `info.last_token_usage` is that call — `input_tokens` (cached ones included), `cached_input_tokens`,
`cache_write_input_tokens`, `output_tokens` (reasoning included) — and `info.total_token_usage` the running total;
the same total repeated (a rate-limit update) is not a new call. `turn_context` lines name the model.
Units are the same ratios as for Claude Code (cache read ×0.1, cache write ×1.25, output ×5): proportions for
comparing roles and runs, not a price. Standard library only.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import sessions  # the Codex build's sessions.py: rollouts(), meta(), records()


def roots_of(cwd: str, also: list) -> list:
    roots = {os.path.realpath(x) for x in [cwd] + also}
    try:  # agents working in a worktree of the repository record that worktree as their folder
        out = subprocess.run(["git", "-C", cwd, "worktree", "list", "--porcelain"], capture_output=True, text=True,
                             timeout=10).stdout
        roots |= {os.path.realpath(l[9:]) for l in out.splitlines() if l.startswith("worktree ")}
    except (OSError, subprocess.TimeoutExpired):
        pass
    return sorted(roots)


def role_of(m: dict) -> str | None:
    """The spawned agent's role, or None for a main session."""
    src = m.get("source")
    spawn = {}
    if isinstance(src, dict):
        sub = src.get("subagent") or src.get("sub_agent") or {}
        if isinstance(sub, dict):
            spawn = sub.get("thread_spawn") or {}
    parent = m.get("parent_thread_id") or spawn.get("parent_thread_id")
    role = m.get("agent_role") or m.get("agent_type") or spawn.get("agent_role") or spawn.get("agent_type")
    if not parent and not role:
        return None
    return role or m.get("agent_nickname") or spawn.get("agent_nickname") or "агент"


def collect(cwd: str, since: str | None, also: list, Agent, add_counts, SESSION: str) -> tuple:
    roots = roots_of(cwd, also)
    session = Agent(SESSION, SESSION)
    agents, beats, active = [], [], 0
    for path in sorted(sessions.rollouts(), key=lambda p: p.stat().st_mtime):
        m = sessions.meta(path)
        where = os.path.realpath(str(m.get("cwd", ""))) if m else ""
        if not m or not any(where == r or where.startswith(r + os.sep) for r in roots):
            continue
        role = role_of(m)
        a = session if role is None else Agent(role, str(m.get("agent_nickname") or "")[:60])
        before, model, last_total = a.calls, "", None
        for d in sessions.records(path):
            ts = (d.get("timestamp") or "")[:19]
            p = d.get("payload") or {}
            if d.get("type") == "turn_context" and p.get("model"):
                model = str(p["model"])
                continue
            if d.get("type") != "event_msg" or p.get("type") != "token_count" or not p.get("info"):
                continue
            if since and ts and ts[:len(since)] < since:
                continue
            info = p["info"]
            total = (info.get("total_token_usage") or {}).get("total_tokens")
            if total is not None and total == last_total:
                continue  # the same running total again: no new call
            last_total = total
            u = info.get("last_token_usage") or {}
            tin, cached, write, out = (int(u.get(k) or 0) for k in
                                       ("input_tokens", "cached_input_tokens", "cache_write_input_tokens", "output_tokens"))
            add_counts(a, max(tin - cached - write, 0), write, 0, cached, out, model, ts)
            if a is session and ts:
                beats.append(ts)
        if role is None:
            active += session.calls > before
        elif a.calls:
            agents.append(a)
    return session, agents, active, beats
