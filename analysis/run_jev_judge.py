"""Evaluate TypeSafe AI Jev model on Cartwheel traces via Vercel AI Gateway.

Evaluates unverified_store_override on Dev (50) and Test (51) splits using the Noul
(boolean) primitive, and generates comparison metrics against gpt-4o-mini.
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import sys
import time
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv()

MODE = "unverified_store_override"
SPLITS_PATH = Path("analysis/state/splits.json")
INPUTS_PATH = Path("analysis/state/hw5_trace_inputs.json")
LABELS_PATH = Path("analysis/state/hw5_labels") / f"{MODE}.jsonl"
PROMPT_V1_PATH = Path("analysis/prompts/unverified_store_override-v1.txt")
JUDGES_DIR = Path("analysis/state/judges")
REPORTS_DIR = Path("analysis/report")
OUTPUT_JUDGE_FILE = JUDGES_DIR / f"{MODE}-jev.json"
OUTPUT_REPORT_FILE = REPORTS_DIR / f"jev-{MODE}.json"

GATEWAY_URL = "https://ai-gateway.vercel.sh/v4/ai/evaluation-model"


def wilson_interval(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """Compute 95% Wilson score confidence interval."""
    if total == 0:
        return 0.0, 1.0
    p_hat = successes / total
    z2 = z * z
    denom = 1.0 + z2 / total
    center = (p_hat + z2 / (2.0 * total)) / denom
    half_width = (z * math.sqrt((p_hat * (1.0 - p_hat) + z2 / (4.0 * total)) / total)) / denom
    return round(max(0.0, center - half_width), 4), round(min(1.0, center + half_width), 4)


def format_trace_to_state(trace_messages: list[dict[str, Any]]) -> str:
    """Format structured messages into a clean chronological transcript."""
    lines = []
    for msg in trace_messages:
        role = msg.get("role", "")
        if role == "user":
            lines.append(f"Customer: {msg.get('text', '')}")
        elif role == "assistant":
            lines.append(f"Assistant: {msg.get('text', '')}")
        elif role == "tool_call":
            args = msg.get("arguments", {})
            lines.append(f"Tool Call: {msg.get('name')}({json.dumps(args)})")
        elif role == "tool_result":
            content = msg.get("content", "")
            c_str = json.dumps(content) if isinstance(content, (dict, list)) else str(content)
            if len(c_str) > 1000:
                c_str = c_str[:1000] + "... [truncated]"
            lines.append(f"Tool Result ({msg.get('name')}): {c_str}")
    return "\n".join(lines)


async def evaluate_trace(
    client: httpx.AsyncClient,
    trace_id: str,
    state_text: str,
    instructions: str,
    headers: dict[str, str],
    semaphore: asyncio.Semaphore,
) -> dict[str, Any]:
    """Call Jev on Vercel AI Gateway for a single trace."""
    payload = {
        "state": state_text,
        "questions": {
            "unverified_store_override": {
                "type": "boolean",
                "instructions": instructions,
            }
        },
    }

    t0 = time.time()
    async with semaphore:
        for attempt in range(3):
            try:
                res = await client.post(GATEWAY_URL, headers=headers, json=payload, timeout=30.0)
                if res.status_code == 200:
                    data = res.json()
                    elapsed_ms = round((time.time() - t0) * 1000, 1)
                    q_ans = data.get("answers", {}).get("unverified_store_override", {})
                    prob = float(q_ans.get("probability", 0.5))
                    cost_str = data.get("providerMetadata", {}).get("gateway", {}).get("cost", "0.00008")
                    return {
                        "trace_id": trace_id,
                        "success": True,
                        "defect_probability": prob,
                        "latency_ms": elapsed_ms,
                        "cost": float(cost_str),
                    }
                else:
                    await asyncio.sleep(1.0 * (attempt + 1))
            except Exception as e:
                if attempt == 2:
                    return {
                        "trace_id": trace_id,
                        "success": False,
                        "error": str(e),
                        "defect_probability": 0.5,
                        "latency_ms": round((time.time() - t0) * 1000, 1),
                        "cost": 0.0,
                    }
                await asyncio.sleep(1.0 * (attempt + 1))

    return {
        "trace_id": trace_id,
        "success": False,
        "error": "Exhausted retries",
        "defect_probability": 0.5,
        "latency_ms": round((time.time() - t0) * 1000, 1),
        "cost": 0.0,
    }


def compute_split_metrics(eval_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute alignment, TPR, TNR, confusion matrix and Wilson intervals."""
    tp = tn = fp = fn = 0
    total = len(eval_rows)
    for r in eval_rows:
        h = r["human_label"]
        j = r["jev_label"]
        if h == 1 and j == 1:
            tp += 1
        elif h == 0 and j == 0:
            tn += 1
        elif h == 1 and j == 0:
            fn += 1  # False alarm (human said Pass, judge cried wolf)
        elif h == 0 and j == 1:
            fp += 1  # Missed defect (human said Bug, judge said Pass)

    agreement = (tp + tn) / total if total > 0 else 0.0
    pass_total = tp + fn  # All human passes
    defect_total = tn + fp  # All human defects

    tpr = tp / pass_total if pass_total > 0 else 0.0
    tnr = tn / defect_total if defect_total > 0 else 0.0

    return {
        "total": total,
        "agreement": round(agreement, 4),
        "tp": tp,
        "tn": tn,
        "fp": fp,
        "fn": fn,
        "tpr": round(tpr, 4),
        "tpr_wilson_ci": wilson_interval(tp, pass_total),
        "tnr": round(tnr, 4),
        "tnr_wilson_ci": wilson_interval(tn, defect_total),
    }


async def main() -> None:
    api_key = os.getenv("AI_GATEWAY_API_KEY")
    if not api_key:
        print("ERROR: AI_GATEWAY_API_KEY not found in environment or .env", file=sys.stderr)
        sys.exit(1)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "ai-model-id": "typesafe-ai/jev",
        "ai-evaluation-model-specification-version": "4",
        "ai-gateway-protocol-version": "0.0.1",
        "Content-Type": "application/json",
    }

    # Load prompt v1
    if not PROMPT_V1_PATH.exists():
        print(f"ERROR: Prompt file {PROMPT_V1_PATH} not found.", file=sys.stderr)
        sys.exit(1)
    prompt_text = PROMPT_V1_PATH.read_text(encoding="utf-8")
    # Clean output instructions
    instructions = prompt_text.split("## Output Format")[0].strip()

    # Load splits
    splits_data = json.loads(SPLITS_PATH.read_text(encoding="utf-8")).get(MODE, {})
    dev_ids = splits_data.get("dev", [])
    test_ids = splits_data.get("test", [])
    target_ids = set(dev_ids + test_ids)
    print(f"Loaded splits: {len(dev_ids)} Dev, {len(test_ids)} Test (Total: {len(target_ids)})")

    # Load trace inputs
    inputs_data = json.loads(INPUTS_PATH.read_text(encoding="utf-8"))
    inputs_by_id = {row["trace_id"]: row["trace"] for row in inputs_data}

    # Load human labels
    human_labels: dict[str, int] = {}
    for line in LABELS_PATH.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            if not row.get("superseded_by"):
                human_labels[row["trace_id"]] = int(row["label"])

    print(f"Starting Jev evaluation on {len(target_ids)} traces via Vercel AI Gateway...")
    semaphore = asyncio.Semaphore(10)  # 10 concurrent requests

    async with httpx.AsyncClient(timeout=45.0) as client:
        tasks = []
        ordered_ids = [tid for tid in dev_ids + test_ids if tid in inputs_by_id]
        for tid in ordered_ids:
            state_text = format_trace_to_state(inputs_by_id[tid])
            tasks.append(evaluate_trace(client, tid, state_text, instructions, headers, semaphore))

        results = await asyncio.gather(*tasks)

    # Process results
    res_by_id = {r["trace_id"]: r for r in results}

    eval_by_split: dict[str, list[dict[str, Any]]] = {"dev": [], "test": []}
    all_evaluations: dict[str, dict[str, Any]] = {}
    predictions_cache: dict[str, int] = {}
    probabilities_cache: dict[str, float] = {}

    for tid in ordered_ids:
        r = res_by_id[tid]
        split = "dev" if tid in dev_ids else "test"
        h_label = human_labels.get(tid, 1)
        prob = r["defect_probability"]
        # Threshold: if defect probability >= 0.5 -> Fail (0), else Pass (1)
        j_label = 0 if prob >= 0.50 else 1
        j_verdict = "Fail" if j_label == 0 else "Pass"
        h_verdict = "Fail" if h_label == 0 else "Pass"
        confidence = prob if j_label == 0 else (1.0 - prob)

        eval_row = {
            "trace_id": tid,
            "split": split,
            "defect_probability": prob,
            "confidence": round(confidence, 4),
            "jev_label": j_label,
            "jev_verdict": j_verdict,
            "human_label": h_label,
            "human_verdict": h_verdict,
            "is_disagreement": (h_label != j_label),
            "latency_ms": r.get("latency_ms", 0),
            "cost": r.get("cost", 0.0),
        }
        eval_by_split[split].append(eval_row)
        all_evaluations[tid] = eval_row
        predictions_cache[tid] = j_label
        probabilities_cache[tid] = prob

    dev_metrics = compute_split_metrics(eval_by_split["dev"])
    test_metrics = compute_split_metrics(eval_by_split["test"])

    # Load gpt-4o-mini judge comparison
    gpt_dev_report = json.loads((REPORTS_DIR / f"dev-{MODE}-v1.json").read_text(encoding="utf-8")) if (REPORTS_DIR / f"dev-{MODE}-v1.json").exists() else {}
    gpt_test_report = json.loads((REPORTS_DIR / f"test-{MODE}-v1.json").read_text(encoding="utf-8")) if (REPORTS_DIR / f"test-{MODE}-v1.json").exists() else {}

    # Save judge state for Review App UI
    judge_export = {
        "judge_id": f"{MODE}-jev",
        "mode": MODE,
        "model": "typesafe-ai/jev",
        "provider": "Vercel AI Gateway",
        "primitive": "noul (boolean)",
        "version": 1,
        "label_convention": "pass_positive",
        "predictions": predictions_cache,
        "probabilities": probabilities_cache,
        "evaluations": all_evaluations,
        "dev_metrics": dev_metrics,
        "test_metrics": test_metrics,
    }
    OUTPUT_JUDGE_FILE.write_text(json.dumps(judge_export, indent=2), encoding="utf-8")
    print(f"Saved Jev judge state to {OUTPUT_JUDGE_FILE}")

    # Save comprehensive report
    report_export = {
        "mode": MODE,
        "model": "typesafe-ai/jev",
        "dev": dev_metrics,
        "test": test_metrics,
        "comparison_with_gpt_4o_mini": {
            "dev": {
                "jev": dev_metrics,
                "gpt_4o_mini": gpt_dev_report,
            },
            "test": {
                "jev": test_metrics,
                "gpt_4o_mini": gpt_test_report,
            },
        },
    }
    OUTPUT_REPORT_FILE.write_text(json.dumps(report_export, indent=2), encoding="utf-8")
    print(f"Saved Jev comparison report to {OUTPUT_REPORT_FILE}")

    # Print summary
    print("\n" + "=" * 60)
    print("🚀 JEV EVALUATION COMPLETED")
    print("=" * 60)
    print(f"DEV SPLIT  ({dev_metrics['total']} traces):")
    print(f"  Agreement: {dev_metrics['agreement']*100:.1f}%")
    print(f"  TPR (Pass Agreement):   {dev_metrics['tpr']*100:.1f}%  CI: {dev_metrics['tpr_wilson_ci']}")
    print(f"  TNR (Defect Catch Rate): {dev_metrics['tnr']*100:.1f}%  CI: {dev_metrics['tnr_wilson_ci']}")
    print(f"  Confusion: TP={dev_metrics['tp']}, TN={dev_metrics['tn']}, FP={dev_metrics['fp']}, FN={dev_metrics['fn']}")
    print("-" * 60)
    print(f"TEST SPLIT ({test_metrics['total']} traces):")
    print(f"  Agreement: {test_metrics['agreement']*100:.1f}%")
    print(f"  TPR (Pass Agreement):   {test_metrics['tpr']*100:.1f}%  CI: {test_metrics['tpr_wilson_ci']}")
    print(f"  TNR (Defect Catch Rate): {test_metrics['tnr']*100:.1f}%  CI: {test_metrics['tnr_wilson_ci']}")
    print(f"  Confusion: TP={test_metrics['tp']}, TN={test_metrics['tn']}, FP={test_metrics['fp']}, FN={test_metrics['fn']}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
