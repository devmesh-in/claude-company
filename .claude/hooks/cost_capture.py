#!/usr/bin/env python3
"""Stop/SubagentStop hook: log per-invocation token usage and an estimated cost.

Registered on both Stop and SubagentStop. On each invocation it reads the
session transcript (JSONL), computes the token DELTA since the last time this
session was seen (via a per-session byte-offset cursor), and appends one
greppable line to company/state/costs.log. It NEVER blocks and ALWAYS exits 0:
this is passive accounting, not enforcement. Everything fails open - on any
error the hook exits 0 silently rather than disturbing a stop.

The delta cursor is the hard invariant: tokens already attributed to a session
are never counted twice, including after a transcript compaction shrinks the
file (OQ-W1-03). Cost is an estimate only, not billing (OQ-W1-01).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as c  # noqa: E402

HOOK = "cost_capture"

_ZEROS = {"in": 0, "out": 0, "cache_r": 0, "cache_w": 0}


def _event_kind(payload):
    """Map the hook event name to the log column. Defaults to stop (OQ-W1-04)."""
    event = payload.get("hook_event_name") or ""
    if event == "SubagentStop":
        return "subagent_stop"
    # "Stop" and anything unexpected/missing fall through to stop.
    return "stop"


def _sum_assistant(lines):
    """Aggregate token usage across assistant lines in an iterable of raw bytes-decoded strings.

    Returns (totals_dict, last_model). Non-parsing lines and lines lacking the
    assistant message/usage shape are skipped silently (read defensively,
    OQ-W1-04). A transcript is JSONL: whole objects appended one per line, so a
    byte range that starts at a prior EOF only ever contains whole lines.
    """
    import json

    totals = dict(_ZEROS)
    last_model = None
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if not isinstance(obj, dict) or obj.get("type") != "assistant":
            continue
        message = obj.get("message")
        if not isinstance(message, dict):
            continue
        model = message.get("model")
        usage = message.get("usage")
        if not isinstance(usage, dict):
            continue

        def _n(key):
            v = usage.get(key, 0)
            return v if isinstance(v, int) else 0

        totals["in"] += _n("input_tokens")
        totals["out"] += _n("output_tokens")
        totals["cache_w"] += _n("cache_creation_input_tokens")
        totals["cache_r"] += _n("cache_read_input_tokens")
        if isinstance(model, str) and model:
            last_model = model
    return totals, last_model


def _read_range(path, start, end):
    """Decode transcript bytes [start, end) into text (utf-8, replace errors)."""
    with open(path, "rb") as f:
        f.seek(start)
        data = f.read(end - start)
    return data.decode("utf-8", "replace")


def _estimate(models_path, model, delta):
    """Return an 'est=$X.XX' string, or None when no pricing applies.

    Reads company/models.json 'pricing' defensively. USD per MTok. Missing rate
    sub-keys default to 0. OQ-W1-01: estimate only, not billing.
    """
    if not model:
        return None
    models = c.read_json_file(models_path)
    pricing = models.get("pricing") if isinstance(models, dict) else None
    if not isinstance(pricing, dict):
        return None
    rate = None
    for key, value in pricing.items():
        if key == "$comment":
            continue
        if isinstance(key, str) and key.lower() in model.lower():
            rate = value
            break
    if not isinstance(rate, dict):
        return None

    def _r(name):
        v = rate.get(name, 0)
        return v if isinstance(v, (int, float)) else 0

    est = (
        delta["in"] * _r("input")
        + delta["out"] * _r("output")
        + delta["cache_w"] * _r("cache_write")
        + delta["cache_r"] * _r("cache_read")
    ) / 1000000.0
    return "est=$%.2f" % est


def main():
    payload = c.read_stdin_json()
    if payload is None:
        sys.exit(0)

    try:
        import json

        root = c.project_root(payload)
        kind = _event_kind(payload)

        transcript_path = payload.get("transcript_path")
        session_id = payload.get("session_id")
        # OQ-W1-03 fail open: no transcript or session, no unreadable file -> no line.
        if not transcript_path or not session_id:
            sys.exit(0)
        if not os.path.isfile(transcript_path):
            sys.exit(0)

        session8 = session_id[:8]

        state_dir = os.path.join(root, "company", "state")
        cursor_path = os.path.join(state_dir, ".cost-cursor.json")
        costs_path = os.path.join(state_dir, "costs.log")
        models_path = os.path.join(root, "company", "models.json")

        cursor = c.read_json_file(cursor_path)
        if not isinstance(cursor, dict):
            cursor = {}
        entry = cursor.get(session_id)
        if not isinstance(entry, dict):
            entry = {"offset": 0, "cum": dict(_ZEROS)}
        prev_offset = entry.get("offset", 0)
        if not isinstance(prev_offset, int) or prev_offset < 0:
            prev_offset = 0
        prev_cum = entry.get("cum")
        if not isinstance(prev_cum, dict):
            prev_cum = dict(_ZEROS)
        prev_cum = {k: (prev_cum.get(k, 0) if isinstance(prev_cum.get(k, 0), int)
                        else 0) for k in _ZEROS}

        size = os.path.getsize(transcript_path)

        if size >= prev_offset:
            # NORMAL: only the freshly-appended byte range is new.
            text = _read_range(transcript_path, prev_offset, size)
            totals, model = _sum_assistant(text.splitlines())
            delta = dict(totals)
            new_offset = size
            new_cum = {k: prev_cum[k] + delta[k] for k in _ZEROS}
        else:
            # COMPACTION: the transcript shrank. Re-read the whole file and take
            # per-key max(0, file_total - cum). Surviving lines were already
            # counted, so this delta is ~0 - the guard against double-counting.
            text = _read_range(transcript_path, 0, size)
            file_total, model = _sum_assistant(text.splitlines())
            delta = {k: max(0, file_total[k] - prev_cum[k]) for k in _ZEROS}
            new_offset = size
            new_cum = {k: max(prev_cum[k], file_total[k]) for k in _ZEROS}

        cursor[session_id] = {"offset": new_offset, "cum": new_cum}

        os.makedirs(state_dir, exist_ok=True)
        with open(cursor_path, "w") as f:
            json.dump(cursor, f)

        total_delta = delta["in"] + delta["out"] + delta["cache_r"] + delta["cache_w"]
        # Log only genuine assistant activity: a model was found and the delta
        # carries tokens. Empty deltas (no new assistant messages, or a
        # compaction that added nothing) persist the cursor but write no line.
        if model is None or total_delta <= 0:
            sys.exit(0)

        task = (c.active_task(root) or {})
        task_slug = task.get("task") if isinstance(task, dict) else None
        task_slug = task_slug or "-"

        tokens = "in=%d out=%d cache_r=%d cache_w=%d" % (
            delta["in"], delta["out"], delta["cache_r"], delta["cache_w"]
        )
        line = "%s | %s | %s | %s | %s | %s" % (
            c.iso_now(), session8, kind, task_slug, model, tokens
        )
        est = _estimate(models_path, model, delta)
        if est is not None:
            line += " | " + est
        line += "\n"

        with open(costs_path, "a") as f:
            f.write(line)
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)

    sys.exit(0)


if __name__ == "__main__":
    main()
