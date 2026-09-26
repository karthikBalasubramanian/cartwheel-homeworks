# Homework 5: 5-Minute Video Presentation Notes & Screen Walkthrough Script

This guide provides the exact timing, screen navigation, talking points, and live terminal commands for your **5-minute single-take video recording** required for Homework 5 (`homework/module-2/hw5.md`).

---

## ⏱️ Video Outline & Timing Breakdown (Max 5 Minutes)

| Segment | Time | Screen to Show | What to Say / Do |
| :--- | :--- | :--- | :--- |
| **1. Definition & Active Learning** | `0:00 - 0:50` | Review App (`http://localhost:8000`) | Define `unverified_store_override`. Explain starting with 7 failures in HW4 and manually labeling 50+ candidates to reach 30+ failures. |
| **2. Metric Framework (TPR, TNR, Wilson CI)** | `0:50 - 1:40` | Review App | Define Label 1 (Pass) vs 0 (Fail). Explain Raw Agreement, TPR (Pass match), TNR (Defect catch), and how the Wilson score interval measures standard error/uncertainty. |
| **3. Prompt Iteration (v0 -> v1)** | `1:40 - 2:30` | Review App filtered to **`Dev Split`** | Explain v0 baseline (86%), walk through 1 specific disagreement (`support-0244`), show how v1 boundary rules reached 94%. |
| **4. Held-Out Test Evaluation** | `2:30 - 3:30` | Review App filtered to **`Test Split`** | Show frozen v1 results: TNR = 91.7%, TPR = 84.6%. Explain Wilson intervals, why TNR is wider than TPR, and why the judge cries wolf. |
| **5. Live Terminal Recalculation** | `3:30 - 4:00` | Terminal | Run the live Python recalculation one-liner to prove test metrics live on camera. |
| **6. Multi-Judge (Jev) & Adoption Verdict** | `4:00 - 5:00` | Review App 3-Judge Console (Right Panel) | Compare GPT-4o-mini with TypeSafe AI Jev (System-1 Noul), discuss `support-0084`, and state your deployment verdict. |

---

## 🎬 Minute-by-Minute Teleprompter Script

### 0:00 – 0:50 | Part 1: Failure Mode Definition & Active Learning Label Collection
* **On Screen:** Open the Review App at `http://localhost:8000`. Point to the header: Mode: `unverified_store_override`.
* **Talking Points:**
  > *"Hi everyone. For Homework 5, I built and evaluated an LLM judge for the failure mode **`unverified_store_override`**.*
  >
  > *Cartwheel is a multi-merchant commerce platform. While the platform has default policies—like a 30-day return window in `cw-returns`—individual merchant stores like Meridian Cycles or Saltbox Pantry have active policy overrides (for example, a 21-day return window or a 15% restocking fee).*
  >
  > *Under specification `AUTH-1` and `TOOL-2`, whenever an assistant advises a customer on return or refund eligibility for an order from a merchant store, it **MUST verify whether that specific store has an active policy override** before answering or issuing a refund.*
  >
  > **Label Collection & Active Learning Enrichment:**
  > *In Homework 4, across our initial 100 traces, we had only identified **6 or 7 confirmed failures** for this mode.*
  > *Because Homework 5 requires at least **30 Fail and 30 Pass labels** to ensure our Train, Dev, and Test splits are large enough to yield meaningful confidence intervals, I used targeted active learning candidate retrieval (`next_to_label` with `strategy='enrich'`) and **manually judged an additional 50 candidate traces**.*
  > *Through this manual enrichment, I reached **32 confirmed failure labels and 94 pass labels (126 total labeled traces)**, which we stratified into **25 Train, 50 Dev, and 51 held-out Test**."*

---

### 0:50 – 1:40 | Part 2: Evaluation Metrics Framework & Wilson Confidence Intervals
* **On Screen:** Point to the split metrics in the Review App console or report.
* **Talking Points:**
  > *"Before looking at the evaluation results, here is how our metrics and statistical uncertainty are defined:*
  >
  > *In Homework 5, our binary label convention is:*
  > * **Label 1 = Positive = PASS** (Conforming conversation — defect is absent).
  > * **Label 0 = Negative = FAIL** (Defect present — `unverified_store_override` occurred).
  >
  > *We track three core metrics:*
  > 
  > 1. **Overall Agreement (Accuracy):**
  >    * `Agreement = (Agreed Passes + Agreed Bugs) / Total Traces`
  >    * *Why Agreement alone is not enough:* In real support workloads, the vast majority of calls are clean passes. A dummy judge that always says 'Pass' could get 85% agreement while catching zero bugs. That is why we must decompose it into TPR and TNR.
  >
  > 2. **True Positive Rate (TPR) — Pass Agreement / Crying Wolf:**
  >    * `TPR = Agreed Passes / Total Human Passes`
  >    * When the human says a conversation passed, how often does the judge agree?
  >    * When TPR is low, the judge is **'crying wolf'**—it is over-policing and falsely flagging innocent conversations as defects.
  >
  > 3. **True Negative Rate (TNR) — Defect Catch Rate:**
  >    * `TNR = Caught Bugs / Total Human Bugs`
  >    * When an actual defect occurs, how often does the judge catch it?
  >    * When TNR is low, the judge is **'sleeping on the job'**—it misses real violations and lets defective behavior slip into production.
  >
  > 4. **Statistical Uncertainty & The Wilson Score Interval:**
  >    * Every evaluation on a finite sample has random sampling noise. A standard deviation tells us how much our measured rate might bounce around if we drew a different sample of traces.
  >    * Standard textbook confidence intervals (the Wald normal approximation) fail badly with small datasets or extreme rates near 0% or 100%—they can produce impossible bounds beyond 100% or zero standard error.
  >    * Instead, we use the **Wilson Score Interval**. The Wilson interval properly accounts for binomial standard deviation by inverting the test score and anchoring around the sample size. It gives us a mathematically robust 95% confidence bracket that never exceeds 0% or 100%, even when our defect pool is small."*

---

### 1:40 – 2:30 | Part 3: Development Hill-Climbing (Prompt v0 -> v1)
* **On Screen:** In the Review App, select the filter: **`🤖 ⚠️ GPT-4o Disagreements (Dev Split) [3]`**.
* **Talking Points:**
  > *"With our 50 Dev traces, we evaluated our baseline prompt, **Prompt v0**. It scored **86.0% agreement** with 7 disagreements.*
  >
  > *When we inspected each disagreement in our review app, we uncovered two root causes:*
  > *1. **Human Label Corrections:** In 3 cases, the human reviewer had accidentally misclicked or missed that a store policy search had occurred.*
  > *2. **Prompt False Alarms:** In 3 cases, the judge penalized the assistant for not checking store policies even when the customer was merely asking a general platform FAQ, or when the assistant was reading raw order metadata without evaluating return eligibility.*
  >
  > *For example, in trace `support-0244`, the customer asked a general clarification before providing an order ID. The v0 judge penalized the assistant for not checking a store policy, even though no order or store had been identified yet!*
  >
  > *To fix this, we created **Prompt v1**, adding 3 strict boundary rules:*
  > * Rule 3: General FAQs without a specific order in scope are Pass.
  > * Rule 4: Data lookups reading raw metadata without return intent are Pass.
  > * Rule 5: Multi-turn disambiguation before order identification is Pass.
  >
  > *This hill-climb brought our Dev agreement from **86.0% up to 94.0%**, with a True Positive Rate of **97.1%** (34 out of 35) and True Negative Rate of **86.7%** (13 out of 15)."*

---

### 2:30 – 3:30 | Part 4: Frozen Held-Out Test Evaluation & Wilson Uncertainty
* **On Screen:** In the Review App, select the filter: **`🔒 Test Split (51) [Held-out Freeze]`**.
* **Talking Points:**
  > *"Once development reached 94% agreement, we **froze Prompt v1** and evaluated our 51 held-out test traces that the prompt had never seen.*
  >
  > *Here are the held-out test results and their Wilson confidence intervals:*
  > * **True Negative Rate (Defect Catch Rate): 91.7%** (11 out of 12 defects caught).
  >   * The 95% Wilson Confidence Interval is **[64.6%, 98.5%]**.
  > * **True Positive Rate (Pass Agreement): 84.6%** (33 out of 39 conforming passes agreed).
  >   * The 95% Wilson Confidence Interval is **[70.3%, 92.8%]**.
  > * **Overall Test Agreement: 86.3%** (44 out of 51 traces matched).
  >
  > **Understanding the Wilson Intervals and Standard Deviation:**
  > * Notice that the Wilson interval for TNR ([64.6% to 98.5%]) is much wider than for TPR ([70.3% to 92.8%]). 
  > * Why? Because our test set has only **12 real defect traces**, compared to **39 pass traces**. In binomial statistics, the standard deviation is inversely proportional to the square root of sample size. With only 12 trials, the standard error is higher, so our uncertainty band is wider: our true defect catch rate in production is with 95% confidence between 65% and 98.5%.
  > * Conversely, for TPR, having 39 traces lowers the standard error and tightens our confidence band down to a 22 percentage-point spread.
  >
  > **Error Directionality:**
  > * Notice the confusion matrix: **11 True Negatives**, **33 True Positives**, only **1 False Positive (missed defect)**, and **6 False Negatives (false alarms)**.*
  > * In other words: **the judge is 6 times more likely to cry wolf than to miss a real bug**. The defect catch rate remained exceptional (91.7%), while TPR dropped slightly on Test due to novel customer phrasing."*

---

### 3:30 – 4:00 | Part 5: Live Metric Recalculation Live on Camera
* **On Screen:** Switch window to your Terminal and run this one-line command:
```bash
uv run python -c "from analysis.helpers import judge_alignment; print(judge_alignment('unverified_store_override-v1', split='test'))"
```
* **Talking Points:**
  > *"To verify complete reproducibility per the assignment requirements, I will now recalculate the test split metrics live from the cached predictions on camera:*
  >
  > *(Point to terminal output)*
  > *As you can see, `judge_alignment` computes:*
  > * `agreement`: 0.8627 (86.3%)
  > * `tnr`: 0.9167 (91.7%) with interval [0.6461, 0.9851]
  > * `tpr`: 0.8462 (84.6%) with interval [0.7027, 0.9275]
  > * `tp`: 33, `tn`: 11, `fp`: 1, `fn`: 6, total `n`: 51.*
  > *The exact numbers match our frozen report."*

---

### 4:00 – 5:00 | Part 6: Multi-Judge Comparison (TypeSafe AI Jev) & Deployment Verdict
* **On Screen:** Switch back to Review App at `http://localhost:8000/?scenario=support-0084`. Show the right panel: **1. Human**, **2. GPT-4o-mini**, **3. TypeSafe AI Jev**.
* **Talking Points:**
  > *"As an extension, we also integrated **TypeSafe AI's Jev** model using the `Noul` binary classification primitive via Vercel AI Gateway.*
  >
  > *Comparing both judges on the right sidebar:*
  > * Both achieved **identical 94.0% agreement on Dev** and **84.6% TPR on Test**.
  > * Jev executes in **~180ms** (System-1 non-autoregressive) at **$0.00008 per evaluation**, versus ~1.8 seconds for GPT-4o-mini.
  >
  > *Look at `support-0084`: The customer asked to cancel a delivered order. The assistant explained that delivered orders cannot be cancelled, read the `refund_eligible: false` field from the order, and referred them to platform disputes. GPT-4o-mini cried wolf and failed the agent, while Jev correctly recognized that this was a platform dispute and cancellation inquiry (Rule 7), outputting defect probability = 0.37 (Pass). Jev resisted the LLM false alarm!*
  >
  > **Final Decision: Would I use this judge?**
  > * **Yes, absolutely—as an automated CI/CD safety gate and regression guard.**
  > * With a **91.7% defect catch rate**, it effectively prevents ungrounded return claims from shipping to production. 
  > * Because its error mode is biased toward **false alarms (crying wolf)** rather than missed bugs, we route judge-flagged traces to human support leads for secondary sign-off rather than auto-penalizing agents. 
  > * Combining GPT-4o-mini's Chain-of-Thought critique with Jev's fast calibrated confidence gives us the ideal two-layer evaluation pipeline."*

---

## 📋 Quick Reference Card for Recording

### File & Artifact Paths
* **Review App URL:** `http://localhost:8000`
* **Test Report File:** `analysis/report/test-unverified_store_override-v1.json`
* **Dev Report File:** `analysis/report/dev-unverified_store_override-v1.json`
* **Jev Report File:** `analysis/report/jev-unverified_store_override.json`
* **Judge Predictions Cache:** `analysis/state/judges/unverified_store_override-v1.json`
* **Prompt v1 File:** `analysis/prompts/unverified_store_override-v1.txt`

### Terminal Cheat Sheet
```bash
# 1. Live Recalculation Command
uv run python -c "from analysis.helpers import judge_alignment; print(judge_alignment('unverified_store_override-v1', split='test'))"

# 2. Jev Recalculation Command (Optional Bonus)
uv run python analysis/run_jev_judge.py
```
