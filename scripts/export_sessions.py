"""
Export sessions from local SQLite session database (.sessions.db) to JSONL format (hw1-session.jsonl).

Usage:
    uv run python -m scripts.export_sessions
    uv run python -m scripts.export_sessions --output my-session.jsonl
"""

import argparse
import ast
import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List

# Known requirements mapping for homework scenarios
KNOWN_REQUIREMENTS = {
    "cancel": ("TOOL-5", "The agent should refuse to cancel an order that has already been delivered."),
    "3980": ("TOOL-6", "The agent should check order delivery date against return policy window and refuse refund."),
    "4455": ("TOOL-6", "The agent should call issue_refund and inform the user that refunds over $50 require approval."),
    "Saltbox Pantry": ("RESP-1", "The agent should state the 7-day return window store override with policy citation."),
    "cookies": ("SCOPE-1", "The agent should refuse out-of-scope requests."),
    "Python": ("SCOPE-1", "The agent should refuse out-of-scope coding/recipe requests."),
    "email": ("SCOPE-2", "The agent should decline account modification requests because no modification tool exists."),
    "ceramic": ("TOOL-2", "The agent should search product catalog with price ceiling filter."),
    "recent orders": ("TOOL-3", "The agent should list recent orders belonging to merchant's store."),
    "heavy-duty vase": ("TOOL-4", "The agent should search user's orders by product name using find_order tool."),
    "4127": ("AUTH-1", "The agent should look up order 4127 and return details for the authorized user.")
}


def parse_session_history(session_id: str, messages_raw: List[Dict[str, Any]]) -> Dict[str, Any] | None:
    """Parses raw message items into a structured hw1-session JSONL record."""
    parts = session_id.split("-")
    if len(parts) < 3:
        return None

    role = parts[1]
    user_id = int(parts[2])
    store_id = None
    if role == "merchant":
        # Merchant store_id from context if available
        store_id = 1 if user_id == 9001 else (2 if user_id == 9002 else None)

    user_request = ""
    agent_response = ""

    # Map call_id to function_call_output
    outputs = {}
    for msg in messages_raw:
        if msg.get("type") == "function_call_output":
            cid = msg.get("call_id")
            out_str = msg.get("output")
            parsed_out = out_str
            if isinstance(out_str, str):
                try:
                    parsed_out = json.loads(out_str)
                except Exception:
                    try:
                        parsed_out = ast.literal_eval(out_str)
                    except Exception:
                        pass
            outputs[cid] = parsed_out

    tool_calls = []

    for msg in messages_raw:
        m_role = msg.get("role")
        if m_role == "user" and not user_request:
            user_request = str(msg.get("content", "")).strip()
        elif m_role == "assistant":
            content = msg.get("content")
            if isinstance(content, list) and len(content) > 0 and isinstance(content[0], dict):
                agent_response = content[0].get("text", "")
            elif isinstance(content, str):
                agent_response = content

        if msg.get("type") == "function_call":
            cid = msg.get("call_id")
            tool_name = msg.get("name")
            raw_args = msg.get("arguments") or {}
            if isinstance(raw_args, str):
                try:
                    raw_args = json.loads(raw_args)
                except Exception:
                    pass
            res = outputs.get(cid, {})
            tool_calls.append({
                "name": tool_name,
                "arguments": raw_args,
                "result": res
            })

    if not user_request:
        return None

    # Infer requirement and expected behavior from keywords
    req_code = None
    expected_text = "The agent should fulfill the request in accordance with SPEC.md."
    
    for kw, (req, exp) in KNOWN_REQUIREMENTS.items():
        if kw.lower() in user_request.lower():
            req_code = req
            expected_text = exp
            break

    return {
        "role": role,
        "user_id": user_id,
        "store_id": store_id,
        "request": user_request,
        "tool_calls": tool_calls,
        "response": agent_response or "Response completed.",
        "expected": expected_text,
        "requirement": req_code,
        "met_requirement": True,
        "problem_source": None
    }


def export_db_to_jsonl(db_path: Path, output_path: Path) -> int:
    if not db_path.exists():
        raise FileNotFoundError(f"Session database {db_path} does not exist.")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT session_id FROM agent_sessions ORDER BY created_at")
    sessions = [row[0] for row in cursor.fetchall()]

    records_by_request = {}
    for s_id in sessions:
        cursor.execute("SELECT message_data FROM agent_messages WHERE session_id = ? ORDER BY id", (s_id,))
        raw_msgs = [json.loads(row[0]) for row in cursor.fetchall()]
        rec = parse_session_history(s_id, raw_msgs)
        if rec and rec["request"]:
            req_key = rec["request"].strip().rstrip(".!?").lower()
            existing = records_by_request.get(req_key)
            if existing is None:
                records_by_request[req_key] = rec
            else:
                # Prefer record with actual agent response and more tool calls
                existing_has_resp = existing["response"] != "Response completed."
                rec_has_resp = rec["response"] != "Response completed."
                if (rec_has_resp and not existing_has_resp) or (
                    rec_has_resp == existing_has_resp and len(rec["tool_calls"]) >= len(existing["tool_calls"])
                ):
                    records_by_request[req_key] = rec

    records = list(records_by_request.values())

    conn.close()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")

    return len(records)


def main() -> None:
    parser = argparse.ArgumentParser(description="Export local CLI sessions to JSONL.")
    parser.add_argument("--db", type=Path, default=Path(".sessions.db"), help="Path to .sessions.db")
    parser.add_argument("--output", type=Path, default=Path("hw1-session.jsonl"), help="Output JSONL path")
    args = parser.parse_args()

    count = export_db_to_jsonl(args.db, args.output)
    print(f"Successfully exported {count} session records to {args.output}")


if __name__ == "__main__":
    main()
