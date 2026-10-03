# Homework 6 Video Presentation Notes & Script

---

## 1. How I Chose the Failure Modes

In Homework 4, I analyzed traces from the Cartwheel AI support assistant and built a failure mode taxonomy grounded in real customer interactions. For Homework 6, I selected **3 failure modes** to construct a comprehensive evaluation suite:

1. **`unverified_store_override`**:
   - *The Problem:* Cartwheel has a default platform return policy (`cw-returns`, 30-day window). However, individual merchant stores (like Saltbox Pantry, Blue Heron Ceramics, Meridian Cycles) can legally set store policy overrides (e.g. 7-day windows or restocking fees).
   - *Defect:* When a shopper asks for a return or RMA on a store's order, the agent often looks at `refund_eligible: true` on the order record and immediately advises or refunds without ever verifying if the specific merchant store has an active policy override.
2. **`unnecessary_tool_call`**:
   - *The Problem:* Tool calls consume latency, tokens, and risk premature state mutations.
   - *Defect:* The agent executes write tools on closed orders (e.g. attempting to cancel delivered orders) or eagerly queries orders without first clarifying ambiguous user requests.
3. **`internal_policy_identifier_leak`**:
   - *The Problem:* Customer-facing support agents should communicate in warm, professional language and provide user-friendly guidance or links.
   - *Defect:* The agent leaks raw backend slugs (`cw-returns`, `cw-store-overrides`) or database column names (`refund_eligible: false`) directly into the customer chat.

---

## 2. Designing the Evaluator Mix & Probing Check Kinds

When authoring cases, I examined the evaluation engine in [`replay/rollout.py`](file:///Users/kabalasu/Documents/work/study/ai-evals/cartwheel-homeworks/replay/rollout.py) to choose the right evaluator for each check:

### Probing Check Kinds:
- I probed whether a `tool_not_called` check exists. I confirmed that `rollout.py` only supports:
  - `tool_called`: Verifies a specific tool was executed at least once.
  - `no_write_tools`: Verifies no write tools (`issue_refund`, `cancel_order`) were executed.
  - `reply_contains` / `reply_not_contains`: Substring checks.
  - `reply_asks_question`: Verifies `?` in the reply.
  - `order_not_status` / `refund_status`: Direct DB state verification.

### Why I Used a Hybrid of Code Checks & LLM Judges:
- **Strict Code Checks vs Semantic Flexibility:** In `rollout.py`, all checks in the `"checks"` array are strict `AND` conditions. 
  - If I required both `tool_called: "search_help_center"` AND `tool_called: "get_policy"`, an efficient agent that finds the store's policy snippet in the search results and stops there would falsely fail!
  - Furthermore, code checks cannot verify *arguments* (e.g., whether the search query was for the right store).
- **The Solution:**
  - For **`unverified_store_override`**, I paired deterministic code checks (`tool_called: "get_order"`, `no_write_tools`) with my **frozen HW5 LLM Judge** (`unverified_store_override-v1`, `gpt-4o-mini`). The LLM judge naturally evaluates the semantic disjunction (did the agent check store policy via `search_help_center` OR `get_policy` before concluding?).
  - For **`unnecessary_tool_call`** and **`internal_policy_identifier_leak`**, I relied on deterministic programmatic code checks (`no_write_tools`, `reply_asks_question`, `reply_not_contains: "cw-returns"`).

---

## 3. Running the Initial 5-Run Baseline & Discovering the Flaw

I authored 10 evaluation cases (`e-001` through `e-010`) and executed **5 baseline trials each** in fresh Docker containers via Harbor (`harbor run -e docker --n-attempts 5`).

### The Initial Results:
- `e-001` to `e-005` were capability cases (pass rates: 0.8, 0.0, 0.0, 0.0, 0.2).
- `e-006` through `e-010` passed **5 out of 5 runs (100%)**, classifying them as `regression`.

### Why I Was Not Satisfied with Baseline Cases `e-008` & `e-009`:
When I inspected the trial transcripts for `e-008` and `e-009`, I realized the prompts were **too easy**:
- The shopper prompt provided an order number: *"How do I return order #62?"*
- **The Escape Hatch:** The agent called `get_order(62)`, saw `refund_eligible: false`, and bluntly replied: *"The refund eligibility status is marked as false, so it can't be returned."*
- Because the agent never looked up return policies in the help center, it never had a reason to cite `cw-returns`.
- The case passed `reply_not_contains: "cw-returns"` simply because it skipped policy lookup entirely, while actually leaking the raw DB field name (`"refund eligibility status"`)!

---

## 4. Hardening the Prompts & Re-Evaluating Baseline

I eliminated the order ID escape hatch by transforming `e-008` and `e-009` into general policy inquiries that **force** the agent to retrieve policy documents:

1. **Hardened `e-008` (General Return Policy):**
   - *User Message:* *"Can you explain Cartwheel's return policy for delivered items? What are the requirements and deadlines?"*
   - *Checks:* `tool_called: "search_help_center"`, `reply_contains: "30"`, `reply_not_contains: "cw-returns"`.
2. **Hardened `e-009` (Store Policy Overrides):**
   - *User Message:* *"Can individual stores on Cartwheel set their own return windows and restocking fees, or is everything strictly platform standard?"*
   - *Checks:* `tool_called: "search_help_center"`, `reply_not_contains: "cw-store-overrides"`, `reply_not_contains: "cw-returns"`.

### Re-Evaluating in Harbor (`hw6-baseline-e008-e009`):
I re-ran Harbor across 5 attempts for both updated cases (10 total trials in Docker):
- **Result: 0 out of 10 passed (0% pass rate)!**
- In every single trial, the agent called `search_help_center`, retrieved the document, and faithfully obeyed the instruction in `SYSTEM_PROMPT_TEMPLATE`:
  > *"Cite the policy id (for example cw-returns) for every policy claim derived from a policy document."*
- In every trial, it literally blurted out: *"policy document with the ID cw-returns"* and *"(policy id: cw-store-overrides)"*.
- This confirmed that `e-008` and `e-009` are genuine **capability failures**.

---

## 5. Final Suite Selection: Choosing 1 Capability & 1 Regression

My final 10-case evaluation suite:
- **7 Capability Cases:** `e-001`, `e-002`, `e-003`, `e-004`, `e-005`, `e-008`, `e-009`
- **3 Regression Cases:** `e-006`, `e-007`, `e-010`

### Why I Selected `e-005` as My In-Depth Capability Case (Part E):
- A 0% case (like `e-002` or `e-008`) has $c = 0$, meaning `pass@k = 0.000` for every $k$. There is no curve or progression to analyze.
- A general FAQ case like `e-001` was too easy (80% baseline).
- **`e-005` (`unnecessary_tool_call` on ambiguous returns)** is the ideal tough capability:
  - Baseline pass rate: **20% (1/5 passes)**.
  - Fails 80% of the time because it eagerly queries `list_my_orders` instead of asking the shopper to clarify which order they mean.
  - Because it has a non-zero pass rate, it allows me to calculate and observe the statistical scaling of `pass@k`.
  - Uses code checks (`no_write_tools`, `reply_asks_question`), making all 15 runs fast and deterministic (0 judge calls).

### Why I Selected `e-006` as My In-Depth Regression Case (Part D):
- **`e-006` (`unnecessary_tool_call` on delivered order cancellation)**:
  - User asks to cancel order #2, which is already marked as delivered.
  - The baseline agent reliably refuses to cancel and calls no write tools (**5 / 5 passes, 100% reliability**).
  - This provides a clean, predictable regression baseline that I can intentionally break in CI.

---

## 6. Deep Dive: Capability Scaling (`pass@k` on Case `e-005`)

### Clarifying Terminology:
- **Trial / Attempt ($n$):** A complete end-to-end execution of a task from initial prompt through tool calling to final reply (NOT a single dialogue turn).
- **Attempt Budget ($k$):** The number of independent candidate attempts given to the model.

### The Mathematics of `pass@k`:
The unbiased estimator formula (Chen et al.):
```text
pass@k = 1 - comb(n - c, k) / comb(n, k)
```
- **$n$:** Total observed trials ($n = 15$).
- **$c$:** Observed successes ($c = 2$).
- **$k$:** The evaluation budget (e.g. $k = 5$).
- **$n - c$:** Observed failures ($13$).

### The Combinatorial Walkthrough ($k = 5$):
1. Total ways to pick 5 trials out of 15:  
   `comb(15, 5) = 3003` combinations.
2. Ways to pick 5 trials that are **pure failures** (from the 13 failed runs):  
   `comb(13, 5) = 1287` combinations.
3. Ways to pick 5 trials that contain **at least one success**:  
   `3003 - 1287 = 1716` combinations.
4. **The Probability:**  
   `1716 / 3003 = 0.5714` (**57.14%**).

Out of all 3,003 possible 5-trial groups, exactly 1,716 contain at least one conforming run!

---

### Empirical 15-Run Results for `e-005` ([`eval_results/e-005-15.json`](file:///Users/kabalasu/Documents/work/study/ai-evals/cartwheel-homeworks/eval_results/e-005-15.json)):

| Observed Trials ($n$) | Successes ($c$) | pass@1 | pass@3 | pass@5 | pass@10 | pass@15 |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **$n = 5$** | 1 | 0.200 | 0.600 | **1.000** | — | — |
| **$n = 10$** | 2 | 0.200 | 0.533 | **0.778** | — | — |
| **$n = 15$** | 2 | 0.133 | 0.371 | **0.571** | 0.905 | **1.000** |

### What These Numbers Teach Us:
1. **Sampling Unlocks Latent Capability:** On any single attempt ($k=1$), the agent only succeeds **13.3%** of the time. But if the system samples **5 attempts** ($k=5$), the chance of at least one success jumps to **57.1%**, and with **10 attempts** ($k=10$), it reaches **90.5%**. The model *has* the capability; it just needs retries or a verifier to extract it.
2. **Sample Size Stabilization ($n$):** If I only ran $n=5$ trials, `pass@5` looked like an overly optimistic 1.000. As I gathered 10 and 15 trials, the estimate stabilized to 0.571, demonstrating why small sample sizes can mislead.
3. **Why Capability Tests Never Block CI:** Because single-attempt reliability is only 13.3%, requiring 5/5 passes in CI would cause unrelated pull requests to fail 87% of the time. CI tracks capability metrics over time, but only gates pull requests on **regression cases**.
