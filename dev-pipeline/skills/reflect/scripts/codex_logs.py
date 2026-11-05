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

import sessions  # the Codex build's sessions.py: rollouts(), meta(), records()


def roots_of(cwd: str, also: list) -> list:
    return sessions.roots_of(cwd, also)


def role_of(m: dict) -> str | None:
    """The spawned agent's role, or None for a main session."""
    return sessions.role_of(m)


def attempt_evidence(record: dict, agent) -> None:
    """Only structured tool/report evidence, never prose or quoted messages."""
    payload = record.get("payload") or {}
    if record.get("type") == "event_msg" and payload.get("type") in ("task_dispatch", "task_report"):
        evidence = payload
    elif record.get("type") == "response_item" and payload.get("type") in ("function_call_output", "custom_tool_call_output"):
        import json
        try:
            evidence = json.loads(payload.get("output", ""))
        except (ValueError, TypeError):
            return
        if not isinstance(evidence, dict) or evidence.get("type") not in ("task_dispatch", "task_report"):
            return
    else:
        return
    if isinstance(evidence.get("task_id"), str):
        agent.task_id = evidence["task_id"]
    if evidence.get("grade") in ("Low", "Mid", "High", "UI", "0"):
        agent.grade = evidence["grade"]
    if isinstance(evidence.get("attempt"), int) and not isinstance(evidence["attempt"], bool) and evidence["attempt"] > 0:
        agent.attempt = evidence["attempt"]
    if evidence.get("review_acceptance") in ("accepted", "rejected"):
        agent.review_acceptance = evidence["review_acceptance"]
    observed = {"task_id": agent.task_id, "grade": agent.grade, "attempt": agent.attempt,
                "review_acceptance": agent.review_acceptance, "units": None,
                "reason": "usage observed per source; per-attempt allocation not observable"}
    if observed not in agent.task_attempts:
        agent.task_attempts.append(observed)
    agent.provenance.append({"kind": "task-evidence", "timestamp": record.get("timestamp")})


def collect(cwd: str, since: str | None, also: list, Agent, add_counts, SESSION: str, until: str | None = None) -> tuple:
    session = Agent(SESSION, SESSION)
    agents, beats, active = [], [], 0
    diagnostics = []
    sources = sessions.project_rollouts(cwd, also, diagnostics=diagnostics)
    metadata = {m.get("id"): m for _, m in sources if m.get("id")}
    seen, agent_by_id = set(), {}
    def logical_id(m):
        current, visited = m, set()
        while sessions.continuation_of(current) in metadata and sessions.continuation_of(current) not in visited:
            previous = sessions.continuation_of(current)
            visited.add(previous)
            current = metadata[previous]
        return current.get("id") or m.get("id")
    for path, m in sources:
        role = role_of(m)
        identity = logical_id(m) or str(path)
        if role is None:
            a = session
        else:
            a = agent_by_id.setdefault(identity, Agent(role, str(m.get("agent_nickname") or "")[:60]))
        before, model, last_total, epoch = a.calls, "", None, 0
        for d in sessions.normalized_records(path, diagnostics):
            ts = d.get("timestamp") or ""
            p = d.get("payload") or {}
            if d.get("type") == "turn_context" and p.get("model"):
                model = str(p["model"])
                continue
            try:
                stamp = sessions.utc(ts)
            except ValueError:
                continue
            in_window = (not since or stamp >= sessions.utc(since)) and (not until or stamp < sessions.utc(until))
            if in_window:
                attempt_evidence(d, a)
            if d.get("type") != "event_msg" or p.get("type") != "token_count":
                continue
            info = p.get("info") if isinstance(p.get("info"), dict) else {}
            total_usage = info.get("total_token_usage") or {}
            total = total_usage.get("total_tokens")
            if total is not None and total == last_total:
                continue  # the same running total again: no new call
            if isinstance(total, int) and isinstance(last_total, int) and total < last_total:
                epoch += 1
            last_total = total
            if not in_window:
                continue
            import json
            key = (identity, epoch, json.dumps(total_usage, sort_keys=True),
                   None if total is not None else (ts, json.dumps(info.get("last_token_usage"), sort_keys=True)))
            if key in seen:
                continue
            seen.add(key)
            u = info.get("last_token_usage")
            a.provenance.append({"kind": "token-count", "source_id": identity, "timestamp": ts, "counter": total})
            if not isinstance(u, dict) or any(not isinstance(u.get(k), int) or isinstance(u.get(k), bool) or u[k] < 0
                                              for k in ("input_tokens", "cached_input_tokens", "output_tokens")):
                a.unknown_usage += 1
                continue
            write = u.get("cache_write_input_tokens", 0)
            if not isinstance(write, int) or isinstance(write, bool) or write < 0 or u["cached_input_tokens"] + write > u["input_tokens"]:
                a.unknown_usage += 1
                continue
            tin, cached, write, out = (int(u.get(k) or 0) for k in
                                       ("input_tokens", "cached_input_tokens", "cache_write_input_tokens", "output_tokens"))
            add_counts(a, max(tin - cached - write, 0), write, 0, cached, out, model, ts)
            if a is session and ts:
                beats.append(ts)
        if role is None:
            active += session.calls > before
    for a in [session, *agent_by_id.values()]:
        has_source = a is not session or any(role_of(m) is None for _, m in sources)
        if has_source and not any(p.get("kind") == "token-count" for p in a.provenance):
            a.unknown_usage += 1
        if len({(item["task_id"], item["attempt"]) for item in a.task_attempts}) > 1:
            a.task_id = a.grade = a.attempt = a.review_acceptance = None
    agents = list(agent_by_id.values())
    session.discovery_diagnostics = diagnostics or ([] if sources else [{"reason": "no project rollout sources"}])
    return session, agents, active, beats
