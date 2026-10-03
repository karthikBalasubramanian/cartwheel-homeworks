# Interface Comparison Report: Cartwheel Trace Review

This report documents the architectural and visual design decisions made for the custom Cartwheel trace review interface (`analysis/review_app/`) compared to the reference interface (`analysis/server.py` and `analysis/ui/index.html`), in accordance with Homework 4 Part A.

---

## 1. One Design Retained from the Reference Interface

**Retained Design:** *File-backed local state mirror with asynchronous Langfuse score synchronization.*

* **Rationale:** The reference interface maintains an inspectable, atomic file-backed JSON store in `analysis/state/` (`annotations.json`, `taxonomy.json`, and `suggestions.json`). We retained this local storage pattern because it ensures:
  1. Complete offline reproducibility and rapid local UI responsiveness without blocking annotators on network roundtrips.
  2. Safe, append-only synchronization to Langfuse scores via `_sync_annotation_scores` when live credentials are configured.
  3. Simple, zero-dependency server execution via Python's standard `http.server.ThreadingHTTPServer`.

---

## 2. One Design Changed After Inspecting Traces

**Changed Design:** *Multi-turn session grouping (`cartwheel.session_id`) with tool-call reconciliation and security permission badges, replacing the flat per-trace paginator.*

* **Observed Problem in Traces:**
  * In `traces/support_traces.json`, there are **260 traces** spanning **250 unique scenarios**. While 240 scenarios are single-turn, 10 scenarios (such as `support-0249`) contain multiple turns.
  * In the reference interface, each turn was presented as an isolated trace. In `support-0249`, Turn 2 began with the user saying: *"It was order #4127 from Blue Heron Ceramics."* Without Turn 1 in view (where the agent listed recent orders and prompted the user for the specific damaged package's order number), Turn 2 appeared detached and un-evaluable.
  * Furthermore, OpenTelemetry splits tool execution into two distinct spans (`GENERATION` for the tool call emission and `TOOL` for execution results), and critical security attributes (`cartwheel.permission_denied`) were buried inside unparsed metadata.
* **Our Solution:**
  1. **Session Grouping:** We group traces by `cartwheel.session_id` into 250 chronological session timelines, rendering Turn 1 and Turn 2 in a unified chat stream.
  2. **Tool Card Reconciliation:** Tool calls and results are reconciled by `call_id` into a single unified visual card.
  3. **Security Badges:** When `cartwheel.permission_denied: true` is present, a prominent red alert badge highlights the refusal reason directly beside the tool call.
  4. **Scenario ID Quick-Jump:** Added direct scenario search (`/api/scenario/{scenario_id}`) and header quick-jump routing so reviewers can navigate directly by scenario number (e.g. `support-0042` or `42`).
  5. **Interactive Axial Coding Workspace (`/axial-codes`):** 
     - *Motivation:* The reference interface provided only sequential trace reading with zero support for Phase 2 axial coding (grouping open coding observations into formal failure modes), forcing annotators to manually cluster notes in spreadsheets.
     - *Implementation:* We built a full-featured Axial Coding dashboard backed by TF-IDF vectorization and agglomerative clustering (`axial_analysis.py`). It features a 2D MDS semantic projection map, pairwise cosine distance matrix, an interactive cluster slider ($k \in [4, 8]$), cluster term extraction, and a custom code injector (used to isolate `unnecessary_tool_call` when qualitative inspection revealed tool call defects lumped with catalog descriptions). Reviewers can refine clusters and click *"Save to Taxonomy"* to directly update `analysis/state/taxonomy.json` and `patterns.json`.

---

## 3. One Limitation Remaining in the Interface

**Remaining Limitation:** *Static snapshot trace ingestion without live bi-directional session pagination from the streaming Langfuse API.*

* **Context:** The review server loads traces at startup from the local snapshot file `traces/support_traces.json`. If a new scenario run or evaluation sweep is launched while the server is running, the server must be restarted to re-index new sessions. A full production implementation would incorporate SSE (Server-Sent Events) or WebSocket notifications from Langfuse to dynamically append newly streamed traces directly into active session timelines.
