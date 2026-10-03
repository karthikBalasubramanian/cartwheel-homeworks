#!/usr/bin/env python3
"""Unified batch generator for Homework 4 (Module 2).

Generates batches from Cartwheel support traces while strictly excluding
all previously reviewed traces in analysis/state/annotations.json.

Supported Batches:
  --batch 3 (or --strategy targeted):
      Depth search targeting candidate failure modes from taxonomy.json (default: 25 traces).
      Implements Part B Batch 3 requirement.

  --batch 4 (or --strategy holdout / uniform):
      Uniform random sampling to test taxonomy stability and theoretical saturation (default: 15 traces).
      Implements Part B Batch 4 requirement.

Usage:
  .venv/bin/python analysis/generate_batch.py --batch 3
  .venv/bin/python analysis/generate_batch.py --batch 4
  .venv/bin/python analysis/generate_batch.py --batch 4 -k 15 --seed 42
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from analysis.helpers.selection import load_traces, next_candidates, select


def generate_batch(
    batch_num: int,
    target_count: int | None = None,
    seed: int = 42,
    taxonomy_path: Path | None = None,
    annotations_path: Path | None = None,
    traces_path: Path | None = None,
    output_path: Path | None = None,
) -> list[dict[str, str]]:
    ann_file = annotations_path or PROJECT_ROOT / "analysis" / "state" / "annotations.json"
    trc_file = traces_path or PROJECT_ROOT / "traces" / "support_traces.json"
    tax_file = taxonomy_path or PROJECT_ROOT / "analysis" / "state" / "taxonomy.json"

    if not ann_file.exists():
        raise FileNotFoundError(f"Annotations file not found: {ann_file}")
    if not trc_file.exists():
        raise FileNotFoundError(f"Traces file not found: {trc_file}")

    all_traces = load_traces(trc_file)
    ann_data = json.loads(ann_file.read_text(encoding="utf-8"))

    # Exclude all previously reviewed traces
    annotations = ann_data.get("annotations", [])
    already_reviewed_ids: set[str] = {
        a["trace_id"] for a in annotations if a.get("trace_id")
    }

    # Map trace_id <-> scenario_id
    id_to_scenario: dict[str, str] = {}
    scenario_to_id: dict[str, str] = {}
    for t in all_traces:
        tid = t["id"]
        scen = t.get("meta", {}).get("scenario_id") or t.get("scenario_id")
        if scen:
            id_to_scenario[tid] = scen
            scenario_to_id[scen] = tid

    remaining_count = len(all_traces) - len(already_reviewed_ids)
    print(f"Loaded {len(all_traces)} traces from {trc_file.name}")
    print(f"Excluded {len(already_reviewed_ids)} previously reviewed traces (Remaining pool: {remaining_count})")

    # ---------------------------------------------------------
    # Batch 3: Targeted Depth Search from taxonomy.json
    # ---------------------------------------------------------
    if batch_num == 3:
        k = target_count or 25
        out_file = output_path or PROJECT_ROOT / "analysis" / "state" / "batch_3_targeted.json"
        if not tax_file.exists():
            raise FileNotFoundError(f"Taxonomy file not found: {tax_file}")

        tax_data = json.loads(tax_file.read_text(encoding="utf-8"))
        modes = tax_data.get("modes", [])
        if not modes:
            raise ValueError(f"No failure modes found in {tax_file}")

        print(f"Generating Batch 3: Targeted Depth Search ({k} traces across {len(modes)} modes)...\n")

        chosen_ids: set[str] = set(already_reviewed_ids)
        per_mode_quota = max(3, (k // len(modes)) + 1)
        mode_candidates: dict[str, list[dict[str, str]]] = {}

        for m in modes:
            mode_name = m.get("name") or m.get("mode")
            positives = m.get("confirmed_positives", [])
            pos_trace_ids = [scenario_to_id[sid] for sid in positives if sid in scenario_to_id]

            cands = next_candidates(
                traces=all_traces,
                mode=mode_name,
                k=per_mode_quota * 3,
                strategy="enrich",
                confirmed_failures=pos_trace_ids,
                already_labeled=chosen_ids,
            )
            mode_candidates[mode_name] = cands

        picks: list[dict[str, str]] = []
        while len(picks) < k:
            added = False
            for m in modes:
                if len(picks) >= k:
                    break
                mode_name = m.get("name") or m.get("mode")
                cands = mode_candidates.get(mode_name, [])
                while cands:
                    cand = cands.pop(0)
                    tid = cand["trace_id"]
                    if tid not in chosen_ids:
                        chosen_ids.add(tid)
                        scen_id = id_to_scenario.get(tid, tid)
                        picks.append({
                            "batch": "batch_3_targeted",
                            "index": len(picks) + 1,
                            "scenario_id": scen_id,
                            "trace_id": tid,
                            "targeted_mode": mode_name,
                            "signal": cand.get("signal", "semantic neighbor"),
                        })
                        added = True
                        break
            if not added:
                break

        payload = {
            "batch_name": "batch_3_targeted",
            "target_count": len(picks),
            "source_taxonomy": str(tax_file.resolve()),
            "traces": picks,
        }

    # ---------------------------------------------------------
    # Batch 4: Uniform Random Holdout for Stability Check
    # ---------------------------------------------------------
    elif batch_num == 4:
        k = target_count or 15
        out_file = output_path or PROJECT_ROOT / "analysis" / "state" / "batch_4_holdout.json"
        print(f"Generating Batch 4: Uniform Random Holdout ({k} traces, seed={seed})...\n")

        raw_picks = select(
            traces=all_traces,
            k=k,
            strategy="random",
            exclude_ids=already_reviewed_ids,
            seed=seed,
        )

        picks = []
        for idx, p in enumerate(raw_picks, 1):
            tid = p["trace_id"]
            scen = id_to_scenario.get(tid, tid)
            picks.append({
                "batch": "batch_4_holdout",
                "index": idx,
                "scenario_id": scen,
                "trace_id": tid,
                "sampling_method": "uniform_random",
                "reason": "Holdout stability check (Batch 4)",
            })

        payload = {
            "batch_name": "batch_4_holdout",
            "target_count": len(picks),
            "sampling_method": "uniform_random",
            "seed": seed,
            "traces": picks,
        }

    else:
        raise ValueError(f"Unsupported batch number: {batch_num}. Use 3 or 4.")

    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    # Print summary table
    print(f"{'#':<3} {'Scenario ID':<14} {'Trace ID':<10} {'Mode / Method':<32} {'Signal / Purpose'}")
    print("-" * 90)
    for p in picks:
        col3 = p.get("targeted_mode") or p.get("sampling_method", "")
        col4 = p.get("signal") or p.get("reason", "")
        print(f"{p['index']:<3} {p['scenario_id']:<14} {p['trace_id'][:8]:<10} {col3:<32} {col4}")
    print("-" * 90)
    print(f"\nSaved {len(picks)} traces to: {out_file.relative_to(PROJECT_ROOT)}")

    return picks


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Unified Batch Generator for Cartwheel Homework 4")
    parser.add_argument(
        "-b", "--batch",
        type=int,
        choices=[3, 4],
        default=4,
        help="Batch number to generate: 3 (Targeted Depth Search) or 4 (Uniform Holdout Stability Check). Default: 4",
    )
    parser.add_argument(
        "-k", "--count",
        type=int,
        default=None,
        help="Number of traces to generate (default: 25 for batch 3, 15 for batch 4)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for holdout sampling (default: 42)",
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        default=None,
        help="Optional custom output path",
    )
    args = parser.parse_args()
    generate_batch(
        batch_num=args.batch,
        target_count=args.count,
        seed=args.seed,
        output_path=args.output,
    )
