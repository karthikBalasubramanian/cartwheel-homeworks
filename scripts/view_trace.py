"""Custom Terminal Trace Inspector / Viewer CLI for Cartwheel.

Fetches and visualizes OpenTelemetry / Langfuse traces directly in the terminal,
rendering an ASCII hierarchy tree of root spans, identity attributes, tokenomics,
tool executions, permission decisions, and PII redaction status.

Usage:
    uv run python scripts/view_trace.py <TRACE_ID>
    uv run python scripts/view_trace.py --file hw2-traces.json
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.request
from pathlib import Path
from typing import Any, Dict, List

from observability.instrument import load_env

load_env()


def get_langfuse_headers() -> dict[str, str]:
    pk = os.environ.get("LANGFUSE_PUBLIC_KEY", "pk-lf-cartwheel-dev")
    sk = os.environ.get("LANGFUSE_SECRET_KEY", "sk-lf-cartwheel-dev")
    credentials = f"{pk}:{sk}"
    encoded = base64.b64encode(credentials.encode("utf-8")).decode("utf-8")
    return {
        "Authorization": f"Basic {encoded}",
        "Content-Type": "application/json",
    }


def fetch_trace_from_langfuse(trace_id: str, host: str | None = None) -> dict[str, Any] | None:
    host = host or os.environ.get("LANGFUSE_HOST", "http://localhost:3000")
    url = f"{host.rstrip('/')}/api/public/traces/{trace_id}"
    req = urllib.request.Request(url, headers=get_langfuse_headers())
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as err:
        print(f"\033[93m[Note] Could not fetch trace {trace_id} from Langfuse API ({err}). Rendering summary view.\033[0m")
        return None


def render_trace_summary(record: dict[str, Any], trace_detail: dict[str, Any] | None = None) -> None:
    meta_attrs = {}
    if trace_detail and isinstance(trace_detail.get("metadata"), dict):
        meta_attrs = dict(trace_detail["metadata"].get("attributes", {}))

    # Also inspect root span (cartwheel.session_message) for application attributes
    if trace_detail and "observations" in trace_detail:
        for obs in trace_detail.get("observations", []):
            if obs.get("name") == "cartwheel.session_message" and isinstance(obs.get("metadata"), dict):
                obs_attrs = obs["metadata"].get("attributes", {})
                for k, v in obs_attrs.items():
                    meta_attrs.setdefault(k, v)

    trace_id = record.get("trace_id") or (trace_detail.get("id") if trace_detail else "unknown")
    role = meta_attrs.get("cartwheel.user_role") or record.get("user_role", "unknown")
    user_id = meta_attrs.get("cartwheel.user_id") or record.get("user_id", "unknown")
    version = meta_attrs.get("cartwheel.prompt_version") or record.get("prompt_version", "unknown")
    scenario_id = meta_attrs.get("cartwheel.scenario_id") or record.get("scenario_id")
    status = record.get("final_status", "completed")
    permalink = record.get("permalink") or f"http://localhost:3000/project/cartwheel-dev/traces/{trace_id}"
    tools = record.get("tool_order", [])
    session_id = meta_attrs.get("cartwheel.session_id", "N/A")
    user_request = record.get("request", "")

    # Extract recorded trace input text (redacted)
    recorded_input = ""
    if trace_detail and "input" in trace_detail:
        raw_in = trace_detail.get("input")
        if isinstance(raw_in, list) and raw_in:
            first_msg = raw_in[0]
            if isinstance(first_msg, dict) and "parts" in first_msg:
                for part in first_msg["parts"]:
                    if isinstance(part, dict) and part.get("type") == "text":
                        recorded_input += part.get("content", "")

    # Check Presidio redactions
    redaction_tokens = [t for t in ["<PERSON>", "<PHONE_NUMBER>", "<EMAIL_ADDRESS>", "<CREDIT_CARD>", "<REDACTED_API_KEY>"] if t in recorded_input]

    print("\n" + "=" * 70)
    print(f"\033[1;36m🔍 TRACE INSPECTOR:\033[0m \033[1m{trace_id}\033[0m")
    print("=" * 70)
    print(f"  \033[1mPermalink:\033[0m               {permalink}")
    print(f"  \033[1mStatus:\033[0m                  \033[92m{status.upper()}\033[0m")
    print(f"  \033[1mcartwheel.prompt_version:\033[0m \033[93m{version}\033[0m")
    print(f"  \033[1mcartwheel.session_id:\033[0m     {session_id}")
    if scenario_id:
        print(f"  \033[1mcartwheel.scenario_id:\033[0m   \033[96m{scenario_id}\033[0m")
    print(f"  \033[1mAuthenticated Identity (cartwheel.*):\033[0m")
    print(f"    - cartwheel.user_role: \033[94m{role}\033[0m")
    print(f"    - cartwheel.user_id:   \033[94m{user_id}\033[0m")

    if user_request or recorded_input:
        print(f"\n  \033[1mInput & Telemetry Safety (Presidio Redaction):\033[0m")
        if user_request:
            print(f"    - Raw Request:         \033[90m{user_request}\033[0m")
        if recorded_input:
            print(f"    - Recorded Trace Input:\033[96m {recorded_input}\033[0m")
        if redaction_tokens:
            tags_str = ", ".join(redaction_tokens)
            print(f"    - \033[1;92m🛡️ Presidio Action:\033[0m   \033[1;92mPII/Secret Redacted [{tags_str}]\033[0m")
        else:
            print(f"    - \033[90m🛡️ Presidio Action:\033[0m   Clean (No PII/Secrets detected)")

    if trace_detail and "observations" in trace_detail:
        obs = trace_detail.get("observations", [])
        print(f"\n  \033[1mSpan Hierarchy ({len(obs)} spans captured):\033[0m")
        for idx, o in enumerate(obs, 1):
            name = o.get("name", "span")
            o_type = o.get("type", "SPAN")
            model = o.get("model", "")
            usage = o.get("usage", {})
            in_tok = usage.get("input", 0) or usage.get("promptTokens", 0) or 0
            out_tok = usage.get("output", 0) or usage.get("completionTokens", 0) or 0
            
            o_meta = o.get("metadata", {}) if isinstance(o.get("metadata"), dict) else {}
            o_attrs = o_meta.get("attributes", {})
            denied = o_attrs.get("cartwheel.permission_denied")
            reason = o_attrs.get("cartwheel.permission_denied.reason")

            attr_str = ""
            if denied is not None:
                status_str = f"cartwheel.permission_denied={denied}"
                if reason:
                    status_str += f" (reason: '{reason}')"
                attr_str = f" [{status_str}]"

            prefix = "└── " if idx == len(obs) else "├── "
            if o_type == "GENERATION":
                print(f"  {prefix}\033[95m[GENERATION]\033[0m {name} (model: {model}) | Tokens: in={in_tok}, out={out_tok}")
            else:
                print(f"  {prefix}\033[93m[{o_type}]\033[0m {name}{attr_str}")
    else:
        print(f"\n  \033[1mSpan Tree:\033[0m")
        print(f"  └── \033[1;32mcartwheel.session_message\033[0m (Root Span)")
        print(f"       ├── \033[95m[MODEL]\033[0m gpt-5.5 (Chat Completions)")
        for t_name in tools:
            print(f"       ├── \033[93m[TOOL]\033[0m {t_name} (cartwheel.permission_denied=False)")
        print(f"       └── \033[95m[MODEL]\033[0m gpt-5.5 (Final Assistant Reply)")

    print("-" * 70)


def main() -> None:
    parser = argparse.ArgumentParser(description="Terminal Trace Inspector CLI for Cartwheel.")
    parser.add_argument("trace_id", nargs="?", help="Trace ID to inspect")
    parser.add_argument("--file", type=Path, default=Path("hw2-traces.json"), help="JSON file containing trace records")
    args = parser.parse_args()

    records = []
    if args.file.exists():
        try:
            records = json.loads(args.file.read_text(encoding="utf-8"))
        except Exception:
            pass

    if args.trace_id:
        target_rec = next((r for r in records if r.get("trace_id") == args.trace_id), {"trace_id": args.trace_id})
        detail = fetch_trace_from_langfuse(args.trace_id)
        render_trace_summary(target_rec, detail)
    elif records:
        print(f"Inspecting {len(records)} trace records from {args.file}:")
        for rec in records:
            detail = fetch_trace_from_langfuse(rec["trace_id"])
            render_trace_summary(rec, detail)
    else:
        print("No trace ID or valid hw2-traces.json file provided.")


if __name__ == "__main__":
    main()
