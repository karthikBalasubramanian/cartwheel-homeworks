# Cartwheel HW4 Review Workflow & Methodology

This document formalizes the grounded theory trace evaluation lifecycle for Homework 4, distinguishing trace selection from human open and axial coding as mandated by `homework/module-2/hw4.md`.

```mermaid
flowchart TD
    subgraph Selection["1. Trace Selection (selection.py)"]
        KMeans["K-Means Feature Clustering<br/>(turns, tool calls, tokens, retrieval)"] --> Reps["15 Cluster Representatives"]
        Uniform["Uniform Random Sampling"] --> Rand15["15 Uniform Random Traces"]
        Reps & Rand15 --> Batch1["Batch 1 (30 Diverse Traces)"]
        RoleStrat["Stratified by Role (Merchant, Support, Shopper)"] --> Batch2["Batch 2 (30 Persona Traces)"]
    end

    subgraph OpenCoding["2. Human Open Coding (Review App)"]
        Batch1 & Batch2 --> Inspect["Inspect Chronological Stream<br/>(Verbatim Deliberation, Tools, Output)"]
        Inspect --> StoppingRule["Apply Stopping Rule:<br/>Identify Earliest Material Failure"]
        StoppingRule --> RawNotes["Record Raw Observations in Notes<br/>(or 'no failure observed')"]
        RawNotes --> Verdict["Assign Initial Verdict (Pass / Fail / Defer)"]
    end

    subgraph AxialCoding["3. Human Axial Coding (Synthesis)"]
        Verdict --> CompareNotes["Compare & Cluster 60+ Human Notes"]
        CompareNotes --> SplitMerge["Apply Split/Merge Rule<br/>(Same product fix = Merge, Different fix = Split)"]
        SplitMerge --> TaxonomyDraft["Draft 5–8 Binary Failure Modes<br/>(Definitions, Boundaries, SPEC.md Mapping)"]
    end

    subgraph TargetedBoundaries["4. Boundary Testing & Validation"]
        TaxonomyDraft --> QueryStore["Semantic Search (selection.py)"]
        QueryStore --> Batch3["Batch 3 (25 Traces)<br/>Candidate Positives & Close Negatives"]
        Batch3 --> RefineTaxonomy["Refine Mode Boundaries"]
        RefineTaxonomy --> Batch4["Batch 4 (15 Traces)<br/>Uniform Random Holdout"]
        Batch4 --> StabilityCheck["Assess Stability:<br/>Count Any New Consequential Modes"]
    end

    subgraph FinalLabeling["5. Structured Labeling (Part E)"]
        StabilityCheck --> BinaryLabel["Apply Final Binary Modes to All 100+ Reviewed Traces"]
        BinaryLabel --> Persist["Persist to analysis/state/labels/*.jsonl & Langfuse Scores"]
    end
```

---

### Key Distinctions in Methodology

1. **Role of `analysis/helpers/selection.py`**:
   - Solely a **trace sampling and retrieval helper**.
   - In Batch 1, it standardizes numeric execution features (`turn_count`, `tool_call_count`, `distinct_tools`, `has_retrieval`, `tokens`) to select diverse traces.
   - It **does not** identify error categories or predict failures.

2. **Role of the Human Reviewer (Open Coding)**:
   - Reads each trace with a blank slate (no pre-assigned categories).
   - Applies the **stopping rule**: stops at the earliest step that violates requirements or materially increases the probability of failure.
   - Records observations in plain English (`analysis/state/annotations.json`).

3. **Axial Coding**:
   - Performed after reviewing batches (e.g. 60 traces across Batches 1 and 2).
   - Groups raw human observations into 5 to 8 formal binary failure modes with boundaries, confirmed positive examples, and close negative examples.
