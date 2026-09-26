"""Review server for Homework 4 (Module 2).

Provides a session-grouped review API and serves the bespoke review UI.
Groups per-turn Cartwheel traces by `cartwheel.session_id` into chronological
conversations, reconciles tool calls and outputs, flags permission denials,
and supports scenario ID lookups alongside Langfuse score sync.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from analysis.review_app.axial_analysis import run_axial_analysis

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent.parent
TRACES_PATH = PROJECT_ROOT / "traces" / "support_traces.json"
STATE_DIR = HERE.parent / "state"
STATIC_DIR = HERE / "static"

STATE_DIR.mkdir(parents=True, exist_ok=True)
STATIC_DIR.mkdir(parents=True, exist_ok=True)

ANNOTATIONS_FILE = STATE_DIR / "annotations.json"
TAXONOMY_FILE = STATE_DIR / "taxonomy.json"
SUGGESTIONS_FILE = STATE_DIR / "suggestions.json"
PATTERNS_FILE = STATE_DIR / "patterns.json"
LABELS_DIR = STATE_DIR / "labels"
HW5_LABELS_DIR = STATE_DIR / "hw5_labels"
JUDGES_DIR = STATE_DIR / "judges"
SPLITS_FILE = STATE_DIR / "splits.json"
REPORTS_DIR = HERE.parent / "report"

LABELS_DIR.mkdir(parents=True, exist_ok=True)
HW5_LABELS_DIR.mkdir(parents=True, exist_ok=True)
JUDGES_DIR.mkdir(parents=True, exist_ok=True)


def _get_judge_data() -> dict[str, Any]:
    """Load latest judge predictions, critiques, splits, and human labels."""
    if not JUDGES_DIR.exists():
        return {}
    judge_files = sorted([f for f in JUDGES_DIR.glob("*.json") if not f.name.startswith("_") and "-jev" not in f.name])
    if not judge_files:
        return {}
    latest_file = judge_files[-1]
    try:
        judge_obj = json.loads(latest_file.read_text(encoding="utf-8"))
    except Exception:
        return {}

    splits_data = _read_json(SPLITS_FILE, {})
    mode = judge_obj.get("mode", "unverified_store_override")
    mode_splits = splits_data.get(mode, {})

    trace_to_split = {}
    for s_name in ("train", "dev", "test"):
        t_ids = mode_splits.get(s_name, [])
        if isinstance(t_ids, list):
            for tid in t_ids:
                trace_to_split[tid] = s_name

    # Load active human labels for mode (HW5 convention: 1=Pass, 0=Fail)
    hw5_labels_file = HW5_LABELS_DIR / f"{mode}.jsonl"
    human_labels = {}
    if hw5_labels_file.exists():
        for line in hw5_labels_file.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    row = json.loads(line)
                    if not row.get("superseded_by"):
                        human_labels[row["trace_id"]] = int(row["label"])
                except Exception:
                    pass

    prompt_hash = judge_obj.get("prompt_hash", "")
    preds = judge_obj.get("predictions", {}).get(prompt_hash, {})
    critiques = judge_obj.get("critiques", {}).get(prompt_hash, {})

    evaluations = {}
    for tid, pred_val in preds.items():
        h_label = human_labels.get(tid)
        j_verdict = "Pass" if pred_val == 1 else "Fail"
        h_verdict = ("Pass" if h_label == 1 else "Fail") if h_label is not None else None
        is_disagree = (h_label is not None and h_label != pred_val)
        evaluations[tid] = {
            "judge_id": judge_obj.get("judge_id"),
            "model": judge_obj.get("model", "gpt-4o-mini"),
            "version": judge_obj.get("version", 0),
            "split": trace_to_split.get(tid),
            "judge_label": pred_val,
            "judge_verdict": j_verdict,
            "human_label": h_label,
            "human_verdict": h_verdict,
            "is_disagreement": is_disagree,
            "critique": critiques.get(tid, ""),
        }

    # Load Jev judge evaluations if available
    jev_file = JUDGES_DIR / f"{mode}-jev.json"
    jev_data = {}
    jev_evaluations = {}
    if jev_file.exists():
        try:
            jev_data = json.loads(jev_file.read_text(encoding="utf-8"))
            jev_evaluations = jev_data.get("evaluations", {})
        except Exception:
            pass

    # Load dev report metrics if available
    judge_id = judge_obj.get("judge_id", "")
    dev_report_file = REPORTS_DIR / f"dev-{judge_id}.json"
    metrics = _read_json(dev_report_file, {}) if dev_report_file.exists() else {}

    return {
        "judge_id": judge_id,
        "model": judge_obj.get("model"),
        "version": judge_obj.get("version"),
        "evaluations": evaluations,
        "jev_evaluations": jev_evaluations,
        "jev_data": jev_data,
        "splits": mode_splits,
        "trace_to_split": trace_to_split,
        "metrics": metrics,
    }

if not ANNOTATIONS_FILE.exists():
    ANNOTATIONS_FILE.write_text(json.dumps({"annotations": []}, indent=2))
if not TAXONOMY_FILE.exists():
    TAXONOMY_FILE.write_text(json.dumps({"modes": []}, indent=2))
if not SUGGESTIONS_FILE.exists():
    SUGGESTIONS_FILE.write_text(json.dumps([], indent=2))


def _ensure_hw5_labels() -> None:
    """Initialize hw5_labels from existing labels with inverted polarity (Pass=1, Fail=0)."""
    if not LABELS_DIR.exists():
        return
    for lfile in LABELS_DIR.glob("*.jsonl"):
        target = HW5_LABELS_DIR / lfile.name
        if not target.exists():
            lines = []
            for line in lfile.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    obj = json.loads(line)
                    hw4_val = int(obj["label"])
                    obj["label"] = 1 - hw4_val  # In HW5: 1 is Pass, 0 is Fail
                    obj["label_id"] = f"{obj['trace_id']}#{obj['label']}"
                    lines.append(json.dumps(obj))
                except Exception:
                    continue
            target.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


_ensure_hw5_labels()


def _append_or_update_label_file(file_path: Path, tid: str, scen: str | None, label_val: int, ts: str) -> None:
    file_path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    found = False
    if file_path.exists():
        for line in file_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                if row.get("trace_id") == tid:
                    row["label"] = label_val
                    row["ts"] = ts
                    row["label_id"] = f"{tid}#{label_val}"
                    if scen and not row.get("scenario_id"):
                        row["scenario_id"] = scen
                    found = True
                rows.append(row)
            except Exception:
                continue
    if not found:
        rows.append({
            "trace_id": tid,
            "scenario_id": scen or "unknown",
            "label": label_val,
            "source": "human",
            "ts": ts,
            "label_id": f"{tid}#{label_val}",
        })
    content = "\n".join(json.dumps(r) for r in rows) + "\n"
    file_path.write_text(content, encoding="utf-8")


def _read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return default


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(path)


def _sync_annotation_scores(data: Any) -> int:
    """Sync labeled annotations to Langfuse scores if configured."""
    try:
        from analysis.helpers import langfuse_io
    except Exception:
        return 0
    if not langfuse_io.is_configured():
        return 0

    annotations = data.get("annotations", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
    written = 0
    client = langfuse_io._client()
    for ann in annotations:
        if not isinstance(ann, dict):
            continue
        trace_id = ann.get("trace_id")
        mode = ann.get("mode")
        label = ann.get("label")
        if not trace_id or not mode or label not in (0, 1, "0", "1"):
            continue
        try:
            langfuse_io.write_label_score(
                trace_id=str(trace_id),
                mode=str(mode),
                label=int(label),
                comment=ann.get("note"),
                client=client,
            )
            written += 1
        except Exception:
            continue
    return written


class TraceStore:
    """Loads and groups traces into chronological sessions."""

    def __init__(self, trace_file: Path = TRACES_PATH):
        self.trace_file = trace_file
        self.sessions: dict[str, dict[str, Any]] = {}
        self.scenario_map: dict[str, str] = {}  # scenario_id -> session_id
        self.trace_map: dict[str, str] = {}  # trace_id -> session_id
        self.scenario_to_trace: dict[str, str] = {}  # scenario_id -> trace_id
        self.ordered_session_ids: list[str] = []
        self.load()
        self.batch1 = self.compute_batch_1()
        self.batch2 = self.compute_batch_2()
        self.batch3 = self.load_batch_3()
        self.batch4 = self.load_batch_4()

    def load(self) -> None:
        if not self.trace_file.exists():
            return

        raw_data = _read_json(self.trace_file, {})
        raw_traces: list[dict[str, Any]] = []
        if isinstance(raw_data, dict):
            raw_traces = raw_data.get("data", raw_data.get("traces", []))
        elif isinstance(raw_data, list):
            raw_traces = raw_data

        session_groups: dict[str, list[dict[str, Any]]] = {}

        for trace in raw_traces:
            trace_id = trace.get("id")
            session_id = trace.get("sessionId")
            meta_attrs = trace.get("metadata", {}).get("attributes", {}) if trace.get("metadata") else {}

            if not session_id and "cartwheel.session_id" in meta_attrs:
                session_id = meta_attrs["cartwheel.session_id"]

            if not session_id:
                for obs in trace.get("observations", []):
                    o_meta = obs.get("metadata", {}).get("attributes", {}) if obs.get("metadata") else {}
                    if "cartwheel.session_id" in o_meta:
                        session_id = o_meta["cartwheel.session_id"]
                        break

            if not session_id:
                session_id = trace_id

            session_groups.setdefault(session_id, []).append(trace)

        # Process each session group
        for session_id, traces in session_groups.items():
            # Sort traces chronologically by timestamp
            traces.sort(key=lambda t: t.get("timestamp") or t.get("createdAt") or "")
            first_trace = traces[0]

            scenario_id = None
            user_id = None
            user_role = "shopper"

            # Extract scenario and user context
            for t in traces:
                if t.get("cartwheel_scenario_id"):
                    scenario_id = t["cartwheel_scenario_id"]
                t_attrs = t.get("metadata", {}).get("attributes", {}) if t.get("metadata") else {}
                if "cartwheel.scenario_id" in t_attrs:
                    scenario_id = t_attrs["cartwheel.scenario_id"]
                if "cartwheel.user_id" in t_attrs:
                    user_id = t_attrs["cartwheel.user_id"]
                if "cartwheel.user_role" in t_attrs:
                    user_role = t_attrs["cartwheel.user_role"]

                for obs in t.get("observations", []):
                    o_attrs = obs.get("metadata", {}).get("attributes", {}) if obs.get("metadata") else {}
                    if not scenario_id and "cartwheel.scenario_id" in o_attrs:
                        scenario_id = o_attrs["cartwheel.scenario_id"]
                    if not user_id and "cartwheel.user_id" in o_attrs:
                        user_id = o_attrs["cartwheel.user_id"]
                    if "cartwheel.user_role" in o_attrs:
                        user_role = o_attrs["cartwheel.user_role"]

            parsed_turns = []
            has_permission_denied = False
            has_escalation = False
            session_tools = set()
            preview_query = ""

            for idx, trace in enumerate(traces, start=1):
                turn_data, turn_denied = self._parse_turn(trace, idx)
                parsed_turns.append(turn_data)
                if turn_denied:
                    has_permission_denied = True
                for step in turn_data.get("steps", []):
                    tname = step.get("tool_name")
                    if tname:
                        session_tools.add(tname)
                        if tname == "escalate_to_human":
                            has_escalation = True
                if not preview_query and turn_data.get("user_input"):
                    preview_query = turn_data["user_input"]

            total_spans = sum(t.get("span_count", 0) for t in parsed_turns)
            total_tool_spans = sum(t.get("tool_span_count", 0) for t in parsed_turns)
            total_gen_spans = sum(t.get("generation_span_count", 0) for t in parsed_turns)

            session_obj = {
                "session_id": session_id,
                "scenario_id": scenario_id or "unknown",
                "user_id": user_id or "unknown",
                "user_role": user_role,
                "turn_count": len(parsed_turns),
                "total_spans": total_spans,
                "tool_spans": total_tool_spans,
                "gen_spans": total_gen_spans,
                "preview_text": preview_query,
                "has_permission_denied": has_permission_denied,
                "has_escalation": has_escalation,
                "tools_called": list(session_tools),
                "turns": parsed_turns,
                "trace_ids": [t.get("id") for t in traces if t.get("id")],
            }

            self.sessions[session_id] = session_obj
            for tid in session_obj["trace_ids"]:
                self.trace_map[tid] = session_id
            if scenario_id:
                self.scenario_map[scenario_id.lower()] = session_id
                num_match = re.search(r"\d+", scenario_id)
                if num_match:
                    self.scenario_map[str(int(num_match.group(0)))] = session_id
                if session_obj["trace_ids"]:
                    self.scenario_to_trace[scenario_id] = session_obj["trace_ids"][0]

        # Sort sessions stably by scenario_id
        self.ordered_session_ids = sorted(
            self.sessions.keys(),
            key=lambda sid: self.sessions[sid].get("scenario_id") or "",
        )

    def _parse_turn(self, trace: dict[str, Any], turn_idx: int) -> tuple[dict[str, Any], bool]:
        trace_id = trace.get("id")
        observations = trace.get("observations", [])
        turn_denied = False

        user_text = ""
        system_prompt = ""
        final_reply = ""
        steps: list[dict[str, Any]] = []

        # Find user query from top-level trace input or session message
        t_input = trace.get("input")
        if isinstance(t_input, list):
            for part_group in t_input:
                for p in part_group.get("parts", []):
                    if p.get("type") == "text" and p.get("content"):
                        user_text = p["content"]
                        break

        # Collect all TOOL observations sorted chronologically
        raw_tool_obs = [obs for obs in observations if obs.get("type") == "TOOL"]
        raw_tool_obs.sort(key=lambda o: o.get("startTime") or "")
        unused_tool_obs = list(raw_tool_obs)

        # Find generations
        generations = [obs for obs in observations if obs.get("type") == "GENERATION"]
        generations.sort(key=lambda g: g.get("startTime") or "")

        total_reasoning_tokens = 0
        total_tokens = 0
        cached_tokens = 0

        for gen in generations:
            attrs = gen.get("metadata", {}).get("attributes", {}) if gen.get("metadata") else {}
            u_details = gen.get("usageDetails", {}) or {}
            total_reasoning_tokens += u_details.get("reasoning_tokens", 0) or int(attrs.get("gen_ai.usage.reasoning_tokens", 0) or 0)
            total_tokens += gen.get("totalTokens", 0) or int(attrs.get("gen_ai.usage.total_tokens", 0) or 0)
            cached_tokens += u_details.get("input_cached_tokens", 0) or int(attrs.get("gen_ai.usage.cache_read.input_tokens", 0) or 0)

            # Check input messages for system prompt
            messages = gen.get("input", {}).get("messages", []) if isinstance(gen.get("input"), dict) else []
            for msg in messages:
                if msg.get("role") == "system" and not system_prompt:
                    for p in msg.get("parts", []):
                        if p.get("content"):
                            system_prompt = p["content"]
                if msg.get("role") == "user" and not user_text:
                    for p in msg.get("parts", []):
                        if p.get("content"):
                            user_text = p["content"]

            # Parse assistant steps
            gen_output = gen.get("output", [])
            has_tool_call = any(
                any(p.get("type") == "tool_call" for p in item.get("parts", []))
                for item in gen_output
            )

            if has_tool_call:
                # In generations with tool calls, text parts are the exact, verbatim pre-tool reasoning
                reasoning_chunks = []
                for item in gen_output:
                    for part in item.get("parts", []):
                        if part.get("type") == "text" and part.get("content"):
                            reasoning_chunks.append(part["content"])
                        elif part.get("type") == "tool_call":
                            tool_name = part.get("name")
                            tool_args = part.get("arguments", {})
                            call_id = part.get("id")

                            # Match corresponding TOOL observation
                            matched_obs = None
                            for idx, o in enumerate(unused_tool_obs):
                                if o.get("name") == tool_name and o.get("input") == tool_args:
                                    matched_obs = unused_tool_obs.pop(idx)
                                    break
                            if not matched_obs:
                                for idx, o in enumerate(unused_tool_obs):
                                    if o.get("name") == tool_name:
                                        matched_obs = unused_tool_obs.pop(idx)
                                        break

                            o_attrs = matched_obs.get("metadata", {}).get("attributes", {}) if matched_obs and matched_obs.get("metadata") else {}
                            is_denied = o_attrs.get("cartwheel.permission_denied") == "true"
                            if is_denied:
                                turn_denied = True

                            steps.append({
                                "reasoning": "\n\n".join(reasoning_chunks),
                                "tool_name": tool_name,
                                "arguments": tool_args,
                                "call_id": call_id,
                                "output": matched_obs.get("output") if matched_obs else None,
                                "permission_denied": is_denied,
                                "permission_denied_reason": o_attrs.get("cartwheel.permission_denied.reason", ""),
                                "latency": matched_obs.get("latency", 0) if matched_obs else 0,
                            })
                            reasoning_chunks = []
            else:
                # In generations without tool calls, text parts form the final assistant response
                reply_chunks = []
                for item in gen_output:
                    for part in item.get("parts", []):
                        if part.get("type") == "text" and part.get("content"):
                            reply_chunks.append(part["content"])
                if reply_chunks:
                    final_reply = "\n\n".join(reply_chunks)

        # Fallback for reply
        if not final_reply and trace.get("output"):
            t_out = trace.get("output")
            if isinstance(t_out, list):
                for p_group in t_out:
                    for p in p_group.get("parts", []):
                        if p.get("type") == "text":
                            final_reply = p.get("content", "")
                            break

        turn_obj = {
            "turn_index": turn_idx,
            "trace_id": trace_id,
            "timestamp": trace.get("timestamp") or trace.get("createdAt") or "",
            "latency": trace.get("latency", 0),
            "user_input": user_text,
            "system_prompt": system_prompt,
            "steps": steps,
            "final_reply": final_reply,
            "span_count": len(observations),
            "tool_span_count": len(raw_tool_obs),
            "generation_span_count": len(generations),
            "other_span_count": max(0, len(observations) - len(raw_tool_obs) - len(generations)),
            "metrics": {
                "total_tokens": total_tokens,
                "reasoning_tokens": total_reasoning_tokens,
                "cached_tokens": cached_tokens,
                "cost": trace.get("totalCost", 0),
            },
        }

        return turn_obj, turn_denied

    def compute_batch_1(self) -> dict[str, dict[str, Any]]:
        """Compute Batch 1: exactly 15 cluster representatives + 15 uniform random samples."""
        import math, random
        sessions = [self.sessions[sid] for sid in self.ordered_session_ids]
        if not sessions:
            return {}

        def get_feat(s: dict[str, Any]) -> list[float]:
            turn_count = float(s.get("turn_count", 1))
            tools = s.get("tools_called", [])
            tool_call_count = float(len(tools))
            distinct_tools = float(len(set(tools)))
            has_retrieval = 1.0 if any("search" in t or "faq" in t or "policy" in t for t in tools) else 0.0
            tokens = 0.0
            for t in s.get("turns", []):
                metrics = t.get("metrics") or {}
                tokens += float(metrics.get("total_tokens", 0) or 0)
            return [turn_count, tool_call_count, distinct_tools, has_retrieval, tokens]

        vectors = [get_feat(s) for s in sessions]
        n_dims = len(vectors[0])
        means = [sum(v[d] for v in vectors) / len(vectors) for d in range(n_dims)]
        stds = []
        for d in range(n_dims):
            var = sum((v[d] - means[d]) ** 2 for v in vectors) / len(vectors)
            stds.append(math.sqrt(var) or 1.0)
        std_vectors = [[(v[d] - means[d]) / stds[d] for d in range(n_dims)] for v in vectors]

        k = 15
        seed = 42
        rng = random.Random(seed)
        init_idx = rng.sample(range(len(std_vectors)), k)
        centroids = [std_vectors[i][:] for i in init_idx]

        for _ in range(25):
            assign = []
            for v in std_vectors:
                dists = [sum((v[d] - c[d]) ** 2 for d in range(n_dims)) for c in centroids]
                assign.append(dists.index(min(dists)))
            new_centroids = []
            for c in range(k):
                members = [std_vectors[i] for i, a in enumerate(assign) if a == c]
                if members:
                    new_centroids.append([sum(m[d] for m in members) / len(members) for d in range(n_dims)])
                else:
                    new_centroids.append(centroids[c])
            centroids = new_centroids

        by_cluster: dict[int, list[int]] = {}
        for i, c in enumerate(assign):
            by_cluster.setdefault(c, []).append(i)

        picks: dict[str, dict[str, Any]] = {}
        chosen_indices: set[int] = set()
        for c in range(k):
            members = by_cluster.get(c, [])
            if members:
                members.sort(key=lambda idx: sum((std_vectors[idx][d] - centroids[c][d]) ** 2 for d in range(n_dims)))
                rep_idx = members[0]
                s = sessions[rep_idx]
                picks[s["session_id"]] = {
                    "type": "cluster_rep",
                    "reason": f"Cluster {c+1} Rep",
                    "cluster": c + 1,
                }
                chosen_indices.add(rep_idx)

        remaining = [i for i in range(len(sessions)) if i not in chosen_indices]
        rng.shuffle(remaining)
        for i in remaining[:15]:
            s = sessions[i]
            picks[s["session_id"]] = {
                "type": "uniform_random",
                "reason": "Uniform Sample",
                "cluster": None,
            }

        return picks

    def compute_batch_2(self) -> dict[str, dict[str, Any]]:
        """Compute Batch 2: 30 traces stratified by user role (10 merchant, 10 support, 10 shopper)."""
        import random
        b1_ids = set(self.batch1.keys())
        remaining = [self.sessions[sid] for sid in self.ordered_session_ids if sid not in b1_ids]

        by_role: dict[str, list[dict[str, Any]]] = {}
        for s in remaining:
            role = s.get("user_role", "shopper")
            by_role.setdefault(role, []).append(s)

        seed = 42
        rng = random.Random(seed)
        picks: dict[str, dict[str, Any]] = {}

        for role in ("merchant", "support", "shopper"):
            candidates = list(by_role.get(role, []))
            rng.shuffle(candidates)
            for s in candidates[:10]:
                picks[s["session_id"]] = {
                    "type": "role_stratified",
                    "reason": f"Role: {role.title()}",
                    "role": role,
                }
        return picks

    def get_by_session_id(self, session_id: str) -> dict[str, Any] | None:
        return self.sessions.get(session_id)

    def load_batch_3(self) -> dict[str, dict[str, Any]]:
        """Load Batch 3 from analysis/state/batch_3_targeted.json."""
        batch3_file = STATE_DIR / "batch_3_targeted.json"
        if not batch3_file.exists():
            return {}
        try:
            data = json.loads(batch3_file.read_text(encoding="utf-8"))
            picks = {}
            for item in data.get("traces", []):
                sid = self.scenario_map.get(item["scenario_id"])
                if sid:
                    picks[sid] = {
                        "type": "targeted_candidate",
                        "reason": f"Target: {item.get('targeted_mode', 'candidate')}",
                        "targeted_mode": item.get("targeted_mode"),
                        "signal": item.get("signal", "semantic neighbor"),
                    }
            return picks
        except Exception:
            return {}

    def load_batch_4(self) -> dict[str, dict[str, Any]]:
        """Load Batch 4 from analysis/state/batch_4_holdout.json."""
        batch4_file = STATE_DIR / "batch_4_holdout.json"
        if not batch4_file.exists():
            return {}
        try:
            data = json.loads(batch4_file.read_text(encoding="utf-8"))
            picks = {}
            for item in data.get("traces", []):
                sid = self.scenario_map.get(item["scenario_id"])
                if sid:
                    picks[sid] = {
                        "type": "holdout_stability",
                        "reason": "Holdout Sample (Batch 4)",
                        "signal": "uniform_random",
                    }
            return picks
        except Exception:
            return {}

    def get_by_scenario_id(self, scenario_id: str) -> dict[str, Any] | None:
        normalized = scenario_id.strip().lower()
        session_id = self.scenario_map.get(normalized)
        if not session_id:
            num = re.search(r"\d+", normalized)
            if num:
                session_id = self.scenario_map.get(str(int(num.group(0))))
        if session_id:
            return self.sessions.get(session_id)
        return None


STORE = TraceStore()


class ReviewAppHandler(BaseHTTPRequestHandler):
    """HTTP Request Handler for Review App."""

    def log_message(self, fmt: str, *args: Any) -> None:
        return

    def _send_json(self, data: Any, status: int = 200) -> None:
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path, content_type: str) -> None:
        if not path.exists():
            self._send_json({"error": f"Not found: {path.name}"}, status=404)
            return
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> Any:
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return None
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return None

    def do_OPTIONS(self) -> None:
        self._send_json({}, status=204)

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        query = self.path.split("?", 1)[1] if "?" in self.path else ""

        if path in ("/", "/index.html"):
            self._send_file(STATIC_DIR / "index.html", "text/html; charset=utf-8")
            return

        if path in ("/axial-codes", "/axial-codes/", "/axial.html"):
            self._send_file(STATIC_DIR / "axial.html", "text/html; charset=utf-8")
            return

        if path.startswith("/static/"):
            rel_path = path[len("/static/"):]
            file_path = STATIC_DIR / rel_path
            if file_path.is_file() and STATIC_DIR in file_path.resolve().parents:
                c_type = "text/plain"
                if rel_path.endswith(".html"):
                    c_type = "text/html; charset=utf-8"
                elif rel_path.endswith(".css"):
                    c_type = "text/css; charset=utf-8"
                elif rel_path.endswith(".js"):
                    c_type = "application/javascript; charset=utf-8"
                elif rel_path.endswith(".json"):
                    c_type = "application/json"
                self._send_file(file_path, c_type)
                return

        # API Routes
        if path == "/api/judge-summary":
            self._send_json(_get_judge_data())
            return

        if path == "/api/sessions":
            # Return list of sessions with annotations summary
            annotations_data = _read_json(ANNOTATIONS_FILE, {"annotations": []})
            anns = annotations_data.get("annotations", []) if isinstance(annotations_data, dict) else annotations_data
            ann_by_trace = {a.get("trace_id"): a for a in anns if isinstance(a, dict)}
            ann_by_session = {a.get("session_id"): a for a in anns if isinstance(a, dict) and a.get("session_id")}

            judge_data = _get_judge_data()
            evals = judge_data.get("evaluations", {})
            jev_evals = judge_data.get("jev_evaluations", {})
            trace_to_split = judge_data.get("trace_to_split", {})

            session_list = []
            for sid in STORE.ordered_session_ids:
                s = STORE.sessions[sid]
                # Check if annotated
                ann = ann_by_session.get(sid)
                if not ann:
                    for tid in s.get("trace_ids", []):
                        if tid in ann_by_trace:
                            ann = ann_by_trace[tid]
                            break

                jeval = None
                jev_eval = None
                split_val = None
                for tid in s.get("trace_ids", []):
                    if tid in trace_to_split:
                        split_val = trace_to_split[tid]
                    if tid in evals and jeval is None:
                        jeval = evals[tid]
                    if tid in jev_evals and jev_eval is None:
                        jev_eval = jev_evals[tid]

                b1_info = STORE.batch1.get(sid)
                b2_info = STORE.batch2.get(sid)
                b3_info = STORE.batch3.get(sid)
                b4_info = STORE.batch4.get(sid)
                session_list.append({
                    "session_id": sid,
                    "scenario_id": s.get("scenario_id"),
                    "user_role": s.get("user_role"),
                    "turn_count": s.get("turn_count"),
                    "total_spans": s.get("total_spans", 0),
                    "tool_spans": s.get("tool_spans", 0),
                    "gen_spans": s.get("gen_spans", 0),
                    "preview_text": s.get("preview_text", "")[:90],
                    "has_permission_denied": s.get("has_permission_denied", False),
                    "has_escalation": s.get("has_escalation", False),
                    "tools_called": s.get("tools_called", []),
                    "batch1": b1_info is not None,
                    "batch1_type": b1_info.get("type") if b1_info else None,
                    "batch1_reason": b1_info.get("reason") if b1_info else None,
                    "batch2": b2_info is not None,
                    "batch2_type": b2_info.get("type") if b2_info else None,
                    "batch2_reason": b2_info.get("reason") if b2_info else None,
                    "batch3": b3_info is not None,
                    "batch3_type": b3_info.get("type") if b3_info else None,
                    "batch3_reason": b3_info.get("reason") if b3_info else None,
                    "batch4": b4_info is not None,
                    "batch4_type": b4_info.get("type") if b4_info else None,
                    "batch4_reason": b4_info.get("reason") if b4_info else None,
                    "is_reviewed": ann is not None,
                    "verdict": ann.get("verdict") or ("pass" if ann.get("label") == 1 else "fail" if ann.get("label") == 0 else None) if ann else None,
                    "note": ann.get("note", "") if ann else "",
                    "judge_verdict": jeval.get("judge_verdict") if jeval else None,
                    "is_disagreement": jeval.get("is_disagreement", False) if jeval else False,
                    "jev_verdict": jev_eval.get("jev_verdict") if jev_eval else None,
                    "jev_probability": jev_eval.get("defect_probability") if jev_eval else None,
                    "jev_confidence": jev_eval.get("confidence") if jev_eval else None,
                    "jev_disagreement": jev_eval.get("is_disagreement", False) if jev_eval else False,
                    "split": split_val or (jeval.get("split") if jeval else None),
                })
            self._send_json({"total": len(session_list), "sessions": session_list})
            return


        if path == "/api/batches/batch1":
            picks = []
            for sid, info in STORE.batch1.items():
                s = STORE.sessions.get(sid)
                if s:
                    picks.append({
                        "session_id": sid,
                        "scenario_id": s.get("scenario_id"),
                        "user_role": s.get("user_role"),
                        "turn_count": s.get("turn_count"),
                        "type": info["type"],
                        "reason": info["reason"],
                    })
            self._send_json({"total": len(picks), "picks": picks})
            return

        if path == "/api/batches/batch2":
            picks = []
            for sid, info in STORE.batch2.items():
                s = STORE.sessions.get(sid)
                if s:
                    picks.append({
                        "session_id": sid,
                        "scenario_id": s.get("scenario_id"),
                        "user_role": s.get("user_role"),
                        "turn_count": s.get("turn_count"),
                        "type": info["type"],
                        "reason": info["reason"],
                    })
            self._send_json({"total": len(picks), "picks": picks})
            return

        if path == "/api/batches/batch3":
            picks = []
            for sid, info in STORE.batch3.items():
                s = STORE.sessions.get(sid)
                if s:
                    picks.append({
                        "session_id": sid,
                        "scenario_id": s.get("scenario_id"),
                        "user_role": s.get("user_role"),
                        "turn_count": s.get("turn_count"),
                        "type": info["type"],
                        "reason": info["reason"],
                    })
            self._send_json({"total": len(picks), "picks": picks})
            return

        if path == "/api/batches/batch4":
            picks = []
            for sid, info in STORE.batch4.items():
                s = STORE.sessions.get(sid)
                if s:
                    picks.append({
                        "session_id": sid,
                        "scenario_id": s.get("scenario_id"),
                        "user_role": s.get("user_role"),
                        "turn_count": s.get("turn_count"),
                        "type": info["type"],
                        "reason": info["reason"],
                    })
            self._send_json({"total": len(picks), "picks": picks})
            return

        if path.startswith("/api/session/"):
            session_id = path[len("/api/session/"):]
            session = STORE.get_by_session_id(session_id)
            if not session:
                self._send_json({"error": f"Session {session_id} not found"}, status=404)
                return

            annotations_data = _read_json(ANNOTATIONS_FILE, {"annotations": []})
            anns = annotations_data.get("annotations", []) if isinstance(annotations_data, dict) else annotations_data
            session_anns = [a for a in anns if a.get("session_id") == session_id or a.get("trace_id") in session.get("trace_ids", [])]

            judge_data = _get_judge_data()
            evals = judge_data.get("evaluations", {})
            jev_evals = judge_data.get("jev_evaluations", {})
            trace_to_split = judge_data.get("trace_to_split", {})
            jeval = None
            jev_eval = None
            split_val = None
            for tid in session.get("trace_ids", []):
                if tid in trace_to_split:
                    split_val = trace_to_split[tid]
                if tid in evals and jeval is None:
                    jeval = evals[tid]
                if tid in jev_evals and jev_eval is None:
                    jev_eval = jev_evals[tid]

            result = dict(session)
            result["annotations"] = session_anns
            result["judge_evaluation"] = jeval
            result["jev_evaluation"] = jev_eval
            result["split"] = split_val
            self._send_json(result)
            return

        if path.startswith("/api/scenario/"):
            scenario_id = path[len("/api/scenario/"):]
            session = STORE.get_by_scenario_id(scenario_id)
            if not session:
                self._send_json({"error": f"Scenario {scenario_id} not found"}, status=404)
                return
            annotations_data = _read_json(ANNOTATIONS_FILE, {"annotations": []})
            anns = annotations_data.get("annotations", []) if isinstance(annotations_data, dict) else annotations_data
            session_anns = [a for a in anns if a.get("session_id") == session["session_id"] or a.get("trace_id") in session.get("trace_ids", [])]

            judge_data = _get_judge_data()
            evals = judge_data.get("evaluations", {})
            jev_evals = judge_data.get("jev_evaluations", {})
            trace_to_split = judge_data.get("trace_to_split", {})
            jeval = None
            jev_eval = None
            split_val = None
            for tid in session.get("trace_ids", []):
                if tid in trace_to_split:
                    split_val = trace_to_split[tid]
                if tid in evals and jeval is None:
                    jeval = evals[tid]
                if tid in jev_evals and jev_eval is None:
                    jev_eval = jev_evals[tid]

            result = dict(session)
            result["annotations"] = session_anns
            result["judge_evaluation"] = jeval
            result["jev_evaluation"] = jev_eval
            result["split"] = split_val
            self._send_json(result)
            return


        if path == "/api/annotations":
            self._send_json(_read_json(ANNOTATIONS_FILE, {"annotations": []}))
            return

        if path in ("/api/taxonomy", "/api/patterns"):
            tax = _read_json(TAXONOMY_FILE, {"modes": []})
            self._send_json(tax)
            return

        if path == "/api/suggestions":
            self._send_json(_read_json(SUGGESTIONS_FILE, []))
            return

        if path == "/api/progress":
            annotations_data = _read_json(ANNOTATIONS_FILE, {"annotations": []})
            anns = annotations_data.get("annotations", []) if isinstance(annotations_data, dict) else annotations_data
            reviewed_sessions = set()
            pass_count = 0
            fail_count = 0
            defer_count = 0

            for a in anns:
                if not isinstance(a, dict):
                    continue
                sid = a.get("session_id")
                if sid:
                    reviewed_sessions.add(sid)
                v = a.get("verdict")
                if v == "pass" or a.get("label") == 1:
                    pass_count += 1
                elif v == "fail" or a.get("label") == 0:
                    fail_count += 1
                elif v == "defer":
                    defer_count += 1

            self._send_json({
                "total_sessions": len(STORE.sessions),
                "reviewed_count": len(reviewed_sessions),
                "remaining_count": max(0, len(STORE.sessions) - len(reviewed_sessions)),
                "verdicts": {
                    "pass": pass_count,
                    "fail": fail_count,
                    "defer": defer_count,
                },
            })
            return

        if path == "/api/axial-analysis":
            k_val = 6
            if query and "k=" in query:
                try:
                    k_match = re.search(r"k=(\d+)", query)
                    if k_match:
                        k_val = int(k_match.group(1))
                except Exception:
                    pass
            annotations_data = _read_json(ANNOTATIONS_FILE, {"annotations": []})
            anns = annotations_data.get("annotations", []) if isinstance(annotations_data, dict) else annotations_data
            result = run_axial_analysis(anns, k_clusters=k_val)
            self._send_json(result)
            return

        if path == "/api/candidates":
            mode = "unverified_store_override"
            k = 35
            strategy = "enrich"
            if query:
                params = urllib.parse.parse_qs(query)
                mode = params.get("mode", [mode])[0]
                try:
                    k = int(params.get("k", [k])[0])
                except (ValueError, TypeError):
                    pass
                strategy = params.get("strategy", [strategy])[0]

            annotations_data = _read_json(ANNOTATIONS_FILE, {"annotations": []})
            anns = annotations_data.get("annotations", []) if isinstance(annotations_data, dict) else annotations_data
            ann_by_trace = {a.get("trace_id"): a for a in anns if isinstance(a, dict)}
            ann_by_session = {a.get("session_id"): a for a in anns if isinstance(a, dict) and a.get("session_id")}

            try:
                from analysis.helpers import next_to_label
                raw_candidates = next_to_label(
                    mode=mode,
                    k=k,
                    strategy=strategy,
                    trace_source=TRACES_PATH,
                )
            except Exception as e:
                self._send_json({"error": str(e), "candidates": []}, status=500)
                return

            candidate_list = []
            for c in raw_candidates:
                tid = c.get("trace_id")
                sid = STORE.trace_map.get(tid)
                s = STORE.sessions.get(sid) if sid else None
                ann = ann_by_session.get(sid)
                if not ann and s:
                    for s_tid in s.get("trace_ids", []):
                        if s_tid in ann_by_trace:
                            ann = ann_by_trace[s_tid]
                            break

                candidate_list.append({
                    "trace_id": tid,
                    "session_id": sid,
                    "scenario_id": s.get("scenario_id") if s else None,
                    "signal": c.get("signal"),
                    "user_role": s.get("user_role") if s else None,
                    "turn_count": s.get("turn_count") if s else 0,
                    "preview_text": s.get("preview_text", "")[:90] if s else "",
                    "tools_called": s.get("tools_called", []) if s else [],
                    "is_reviewed": ann is not None,
                    "verdict": ann.get("verdict") if ann else None,
                })

            # Also compute current Pass/Fail counts for this mode
            labels_file = STATE_DIR / "labels" / f"{mode}.jsonl"
            hw5_file = STATE_DIR / "hw5_labels" / f"{mode}.jsonl"
            fail_count = 0
            pass_count = 0
            if hw5_file.exists():
                for line in hw5_file.read_text(encoding="utf-8").splitlines():
                    if line.strip():
                        try:
                            obj = json.loads(line)
                            if obj.get("label") == 1:
                                pass_count += 1
                            elif obj.get("label") == 0:
                                fail_count += 1
                        except Exception:
                            pass
            elif labels_file.exists():
                for line in labels_file.read_text(encoding="utf-8").splitlines():
                    if line.strip():
                        try:
                            obj = json.loads(line)
                            if obj.get("label") == 1:
                                fail_count += 1
                            elif obj.get("label") == 0:
                                pass_count += 1
                        except Exception:
                            pass

            self._send_json({
                "mode": mode,
                "strategy": strategy,
                "total": len(candidate_list),
                "candidates": candidate_list,
                "stats": {
                    "mode": mode,
                    "fails": fail_count,
                    "passes": pass_count,
                    "target_fails": 35,
                    "target_passes": 30,
                },
            })
            return

        self._send_json({"error": f"unknown path: {path}"}, status=404)

    def do_POST(self) -> None:
        path = self.path.split("?", 1)[0]
        data = self._read_body()
        if data is None:
            self._send_json({"error": "expected a JSON body"}, status=400)
            return

        if path == "/api/annotations":
            # Save annotation(s)
            existing = _read_json(ANNOTATIONS_FILE, {"annotations": []})
            current_list = existing.get("annotations", []) if isinstance(existing, dict) else existing

            new_items = data.get("annotations", [data]) if isinstance(data, dict) and "annotations" in data else ([data] if isinstance(data, dict) else data)

            # Update or append by session_id/trace_id
            for item in new_items:
                if not isinstance(item, dict):
                    continue
                sid = item.get("session_id")
                tid = item.get("trace_id")
                scen = item.get("scenario_id") or (STORE.sessions.get(sid, {}).get("scenario_id") if sid else None)
                if not tid and sid and sid in STORE.sessions and STORE.sessions[sid].get("trace_ids"):
                    tid = STORE.sessions[sid]["trace_ids"][0]
                    item["trace_id"] = tid

                replaced = False
                for idx, curr in enumerate(current_list):
                    if (sid and curr.get("session_id") == sid) or (tid and curr.get("trace_id") == tid):
                        current_list[idx] = item
                        replaced = True
                        break
                if not replaced:
                    current_list.append(item)

                # Synchronize mode labels if provided
                modes = item.get("modes", {})
                verdict = item.get("verdict")
                if tid and isinstance(modes, dict):
                    now_ts = item.get("ts") or dt.datetime.now(dt.timezone.utc).isoformat()
                    for m_name, is_checked in modes.items():
                        # In HW4 labels: 1 = Failure present, 0 = Failure absent
                        # In HW5 labels: 1 = Pass, 0 = Fail
                        is_failure = bool(is_checked and verdict != "pass")
                        hw4_val = 1 if is_failure else 0
                        hw5_val = 0 if is_failure else 1

                        _append_or_update_label_file(
                            LABELS_DIR / f"{m_name}.jsonl",
                            tid=tid,
                            scen=scen,
                            label_val=hw4_val,
                            ts=now_ts,
                        )
                        _append_or_update_label_file(
                            HW5_LABELS_DIR / f"{m_name}.jsonl",
                            tid=tid,
                            scen=scen,
                            label_val=hw5_val,
                            ts=now_ts,
                        )

            payload = {"annotations": current_list}
            _write_json(ANNOTATIONS_FILE, payload)

            synced = _sync_annotation_scores(payload)
            self._send_json({"ok": True, "count": len(current_list), "langfuse_synced": synced})
            return

        if path == "/api/suggestions":
            _write_json(SUGGESTIONS_FILE, data)
            self._send_json({"ok": True})
            return

        if path in ("/api/taxonomy/save", "/api/taxonomy"):
            _write_json(TAXONOMY_FILE, data)
            _write_json(PATTERNS_FILE, data)
            modes_count = len(data.get("modes", [])) if isinstance(data, dict) else (len(data) if isinstance(data, list) else 0)
            self._send_json({"ok": True, "saved_modes": modes_count})
            return

        self._send_json({"error": f"cannot POST to {path}"}, status=404)


def main() -> None:
    parser = argparse.ArgumentParser(description="Cartwheel Review App Server (HW4)")
    parser.add_argument("--port", type=int, default=8000, help="Port to serve on (default: 8000)")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host address (default: 127.0.0.1)")
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), ReviewAppHandler)
    print(f"Cartwheel Review App running at http://{args.host}:{args.port}")
    print(f"Loaded {len(STORE.sessions)} sessions from {TRACES_PATH}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server.")
        server.server_close()


if __name__ == "__main__":
    main()
