"""Run and evaluate LLM judges for Cartwheel failure modes.

Homework 5 workflow:
- Part B: prepare inputs (hw5_trace_inputs.json) and split labels (splits.json)
- Part C: register and run development batches with DocETL
- Part D: freeze judge and evaluate held-out test split
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()

from analysis.helpers import (
    freeze_judge,
    judge_alignment,
    register_judge,
    run_judge,
    split_labels,
)
from analysis.helpers.normalization import _messages
from analysis.helpers.tools import _load_labels

MODE = "unverified_store_override"

TRACES_PATH = Path("traces/support_traces.json")
LABELS_PATH = Path("analysis/state/hw5_labels") / f"{MODE}.jsonl"
INPUTS_PATH = Path("analysis/state/hw5_trace_inputs.json")
SPLITS_PATH = Path("analysis/state/splits.json")
REPORTS_DIR = Path("analysis/report")

# Default CARTWHEEL_JUDGE_TRACE_SOURCE if not already exported
if "CARTWHEEL_JUDGE_TRACE_SOURCE" not in os.environ:
    os.environ["CARTWHEEL_JUDGE_TRACE_SOURCE"] = str(INPUTS_PATH.resolve())



def prepare_inputs(
    traces_path: Path = TRACES_PATH,
    labels_path: Path = LABELS_PATH,
    output_path: Path = INPUTS_PATH,
) -> list[dict[str, Any]]:
    """Read labeled traces, format messages/tools, and strip labels/metadata."""
    if not traces_path.exists():
        raise FileNotFoundError(f"Traces file not found: {traces_path}")
    if not labels_path.exists():
        raise FileNotFoundError(f"Labels file not found: {labels_path}")

    # Load active labeled trace IDs
    labels_data = _load_labels(MODE)
    eligible_ids = {row["trace_id"] for row in labels_data}
    print(f"Found {len(eligible_ids)} active labeled traces in {labels_path}")

    # Load raw traces
    with open(traces_path, "r", encoding="utf-8") as f:
        raw_export = json.load(f)

    raw_traces = raw_export.get("traces", []) if isinstance(raw_export, dict) else raw_export
    raw_by_id = {t["id"]: t for t in raw_traces if "id" in t}

    records: list[dict[str, Any]] = []
    missing_ids = []

    for tid in sorted(eligible_ids):
        if tid not in raw_by_id:
            missing_ids.append(tid)
            continue
        raw_trace = raw_by_id[tid]
        # Format messages cleanly using normalized message parser
        messages = _messages(raw_trace)

        # Build clean record containing ONLY trace_id and trace
        # Strip all scenario IDs, review notes, and label metadata to avoid data leakage
        clean_record = {
            "trace_id": tid,
            "trace": messages,
        }
        records.append(clean_record)

    if missing_ids:
        raise ValueError(f"Could not find {len(missing_ids)} labeled trace IDs in {traces_path}: {missing_ids[:5]}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)

    print(f"Saved {len(records)} clean input records to {output_path}")
    return records


def split_data(
    mode: str = MODE,
    inputs_path: Path = INPUTS_PATH,
    fractions: tuple[float, float, float] = (0.20, 0.40, 0.40),
    seed: int = 7,
    min_per_class: int = 10,
) -> dict[str, list[str]]:
    """Split active labeled data into train, dev, and test sets."""
    if not inputs_path.exists():
        raise FileNotFoundError(f"Input records not found: {inputs_path}. Run prepare_inputs() first.")

    with open(inputs_path, "r", encoding="utf-8") as f:
        records = json.load(f)

    eligible_trace_ids = [r["trace_id"] for r in records]

    splits = split_labels(
        mode=mode,
        fractions=fractions,
        seed=seed,
        min_per_class=min_per_class,
        eligible_trace_ids=eligible_trace_ids,
    )

    # Calculate and report class counts
    # Note: in _load_labels internal representation: 1=Fail, 0=Pass
    labels = {r["trace_id"]: r["label"] for r in _load_labels(mode)}

    print(f"\n=== Data Splits for '{mode}' (Seed={seed}, Fractions={fractions}) ===")
    for split_name in ["train", "dev", "test"]:
        s_ids = splits.get(split_name, [])
        # HW5 convention: 1=Pass, 0=Fail
        passes = sum(1 for tid in s_ids if labels.get(tid) == 0)
        fails = sum(1 for tid in s_ids if labels.get(tid) == 1)
        print(f"  {split_name.upper():5s}: {len(s_ids):2d} traces | Passes (1) = {passes:2d} | Fails (0) = {fails:2d}")

    return splits


def run_development(
    mode: str = MODE,
    prompt_path: str | Path = Path("analysis/prompts/unverified_store_override-v0.txt"),
    judge_model: str = "gpt-4o-mini",
    batch_size: int = 10,
) -> dict[str, Any]:
    """Register prompt, evaluate dev split with DocETL, and calculate alignment."""
    prompt_file = Path(prompt_path)
    if not prompt_file.exists():
        raise FileNotFoundError(f"Prompt file not found: {prompt_file}")

    prompt_text = prompt_file.read_text(encoding="utf-8")
    record = register_judge(
        mode=mode,
        prompt_text=prompt_text,
        judge_model=judge_model,
    )
    judge_id = record["judge_id"]
    version = record["version"]
    print(f"Registered judge '{judge_id}' (version {version}) with model '{judge_model}'")

    print(f"Running judge '{judge_id}' on DEV split (batch size {batch_size})...")
    run_judge(judge_id, split="dev", batch_size=batch_size)

    development = judge_alignment(judge_id, split="dev")

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_file = REPORTS_DIR / f"dev-{judge_id}.json"
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(development, f, indent=2)

    print(f"Saved dev evaluation report to {report_file}")
    _print_metrics_summary("DEV", development)
    return {"judge_id": judge_id, "metrics": development}


def run_test(judge_id: str, batch_size: int = 10) -> dict[str, Any]:
    """Freeze judge, run on test split once, and save test metrics."""
    print(f"Freezing judge '{judge_id}'...")
    freeze_judge(judge_id)

    print(f"Running frozen judge '{judge_id}' on TEST split (batch size {batch_size})...")
    run_judge(judge_id, split="test", batch_size=batch_size)

    test_metrics = judge_alignment(judge_id, split="test")

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_file = REPORTS_DIR / f"test-{judge_id}.json"
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(test_metrics, f, indent=2)

    print(f"Saved test evaluation report to {report_file}")
    _print_metrics_summary("TEST", test_metrics)
    return test_metrics


def _print_metrics_summary(split_name: str, metrics: dict[str, Any]) -> None:
    tp = metrics.get("tp", 0)
    fp = metrics.get("fp", 0)
    fn = metrics.get("fn", 0)
    tn = metrics.get("tn", 0)
    tpr = metrics.get("tpr", 0.0)
    tnr = metrics.get("tnr", 0.0)
    tpr_ci = metrics.get("tpr_interval", [0.0, 0.0])
    tnr_ci = metrics.get("tnr_interval", [0.0, 0.0])
    agreement = metrics.get("agreement", 0.0)
    n = metrics.get("n", 0)

    print(f"\n=== {split_name} Evaluation Summary (N={n}) ===")
    print(f"  Confusion Matrix: TP={tp}, FP={fp}, FN={fn}, TN={tn}")
    print(f"  Overall Agreement: {agreement:.3f} ({tp + tn}/{n})")
    print(f"  TPR (Pass Agreement): {tpr:.3f} (95% CI: [{tpr_ci[0]:.3f}, {tpr_ci[1]:.3f}])")
    print(f"  TNR (Fail Agreement): {tnr:.3f} (95% CI: [{tnr_ci[0]:.3f}, {tnr_ci[1]:.3f}])")


def main() -> None:
    parser = argparse.ArgumentParser(description="Cartwheel HW5 LLM Judge Runner")
    parser.add_argument("--prepare", action="store_true", help="Prepare inputs and generate data splits")
    parser.add_argument("--dev", type=str, help="Run development on a prompt file, e.g. analysis/prompts/unverified_store_override-v0.txt")
    parser.add_argument("--test", type=str, help="Freeze and run test for a judge ID, e.g. unverified_store_override-v0")
    parser.add_argument("--model", type=str, default="gpt-4o-mini", help="Judge model (default: gpt-4o-mini)")

    args = parser.parse_args()

    if args.prepare:
        prepare_inputs()
        split_data()
    elif args.dev:
        run_development(prompt_path=args.dev, judge_model=args.model)
    elif args.test:
        run_test(judge_id=args.test)
    else:
        # Default behavior: run prepare_inputs and split_data
        prepare_inputs()
        split_data()


if __name__ == "__main__":
    main()
