# Raindrop Workshop & Raw Trace Debugger Inspection Notes

## 1. Trace Inspection Scope
To complement human open coding, execution-level inspection was conducted across representative execution paths spanning Shopper, Merchant, and Support caller contexts, focusing on tool execution parameters, deliberation tokens, and model response generation.

- **Run Identifiers Inspected:**
  - `run-wk-001` (Scenario: `support-0196`, Role: `shopper`, Tools: `search_products`)
  - `run-wk-002` (Scenario: `support-0238`, Role: `shopper`, Tools: `list_my_orders`)
  - `run-wk-003` (Scenario: `support-0059`, Role: `merchant`, Tools: `get_order`, `get_policy`)
  - `run-wk-004` (Scenario: `support-0211`, Role: `support`, Tools: `get_order`, `issue_refund`)
  - `run-wk-005` (Scenario: `support-0244`, Role: `shopper`, Tools: `list_my_orders`, `issue_refund`)

---

## 2. Execution-Level Findings & Candidate Behaviors

1. **Redundant Pre-Invocation Tool Deliberation (`run-wk-001`, `run-wk-002`):**
   - *Observation:* Raw inspection of model deliberation revealed that the agent recognized all necessary parameters were already in context, yet invoked `search_products` and `list_my_orders` due to a heuristic system prompt bias favoring explicit tool verification.
   - *Taxonomy Impact:* Confirmed the emergence of `unnecessary_tool_call` as an independent trajectory defect.

2. **Internal Policy Slug Leakage in Output Token Generation (`run-wk-003`):**
   - *Observation:* The agent's deliberation correctly analyzed `cw-returns` and `cw-store-overrides`, but the completion generation copied raw policy identifiers verbatim into customer markdown output.
   - *Taxonomy Impact:* Reinforced `internal_policy_identifier_leak` as a deterministic code-evaluable failure mode.

3. **Ambiguous Pre-Refund Reasoning vs. Unsolicited Action (`run-wk-005`):**
   - *Alternative Explanation / Uncertainty Case:* In `support-0244`, the coding agent initially hypothesized a permission violation. However, inspection of the multi-turn session revealed that the agent guessed an order ID (#6428) rather than clarifying per `RESP-3`, triggering an erroneous write operation that had to be rolled back on turn 2.
   - *Taxonomy Impact:* Classified under `unverified_store_override` and `unsolicited_action_execution`.

---

## 3. Workshop Suggestions Disposition
- **Suggestion 1 (Tool Call Pruning):** Accepted $\rightarrow$ codified as `unnecessary_tool_call`.
- **Suggestion 2 (Policy Citation Refinement):** Revised $\rightarrow$ distinguished internal slug leakage from compliant policy citation.
- **Suggestion 3 (General Token Budget Anomaly):** Rejected $\rightarrow$ variation in token length correlated with multi-turn order histories, not a distinct operational failure mode.
