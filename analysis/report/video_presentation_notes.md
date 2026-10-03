# Homework 5: 5-Minute Video Presentation Notes & Screen Walkthrough Script

This guide provides the exact timing, screen navigation, talking points, and specific scenario examples for your **5-minute single-take video recording** required for Homework 5 (`homework/module-2/hw5.md`).

---

## ⏱️ Video Outline & Timing Breakdown (Max 5 Minutes)

| Segment | Time | Screen to Show | What to Say / Do |
| :--- | :--- | :--- | :--- |
| **1. Definition & Active Learning** | `0:00 - 0:50` | Review App (`http://localhost:8000`) | Define `unverified_store_override`. Explain starting with 7 failures in HW4 and manually labeling 50+ candidates to reach 30+ failures. |
| **2. Metrics & Wilson Standard Deviation** | `0:50 - 1:45` | Review App | Define Label 1 (Pass) vs 0 (Fail). Explain Agreement, TPR (Pass match), TNR (Defect catch). Deep-dive into binomial standard deviation, sample size effects, and Wilson score intervals. |
| **3. Prompt Iteration (v0 -> v1)** | `1:45 - 2:30` | Review App filtered to **`Dev Split`** | Explain v0 baseline (86%), walk through root causes of disagreements, and show how v1 boundary rules reached 94% on Dev. |
| **4. GPT-4o Disagreement Walkthrough** | `2:30 - 3:20` | Review App at `http://localhost:8000/?scenario=support-0229` | Show where GPT-4o disagrees with Human on Test (`support-0229`: Human Pass vs GPT Fail). Explain the judge crying wolf and test metrics (TNR 91.7%, TPR 84.6%). |
| **5. Jev Disagreement Walkthrough** | `3:20 - 4:20` | Review App at `http://localhost:8000/?scenario=support-0084` | Introduce TypeSafe AI Jev (System-1 Noul). Show where Jev disagrees with Human (`support-0084`: Human Fail vs Jev Pass). Explain how Jev resisted the false alarm. |
| **6. Adoption Verdict & Pipeline Architecture** | `4:20 - 5:00` | Review App 3-Judge Console | State production verdict: Deploy as CI/CD safety net. Explain why high TNR protects merchants, and how combining Jev + GPT-4o creates a two-tiered evaluation system. |

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

### 0:50 – 1:45 | Part 2: Evaluation Metrics Framework & Wilson Standard Deviation
* **On Screen:** Point to the split metrics in the Review App console or test report summary.

#### 📊 Metric Framework Table (Easy Readout)

| Metric | Plain English Formula | What It Measures | If Low, the Judge Is... |
| :--- | :--- | :--- | :--- |
| **Overall Agreement** | `(Agreed Passes + Agreed Bugs) / Total` | Overall accuracy with human labels | Unreliable |
| **True Positive Rate (TPR)** | `Agreed Passes / Total Human Passes` | Pass approval rate (conforming calls) | **"Crying Wolf"** (falsely flagging innocent calls) |
| **True Negative Rate (TNR)** | `Caught Bugs / Total Human Bugs` | Defect catch rate (real bugs caught) | **"Sleeping on the Job"** (missing genuine bugs) |

* **Talking Points:**
  > *"Here is how our metrics and statistical uncertainty are structured:
  >
  > *In Homework 5, our binary label convention is:*
  > * **Label 1 = Positive = PASS** (Conforming conversation — defect is absent).
  > * **Label 0 = Negative = FAIL** (Defect present — `unverified_store_override` occurred).
  >
  > *(Read directly from the table)*
  > * **Agreement:** Measures overall accuracy. But because most support calls are clean passes, a naive judge that always passes everything could score high agreement while catching zero bugs. That is why we decompose it into TPR and TNR.
  > * **True Positive Rate (TPR):** Measures how often the judge agrees when a conversation passed. When TPR is low, the judge is **crying wolf**—over-policing and falsely accusing innocent agents of bugs.
  > * **True Negative Rate (TNR):** Measures how often the judge catches an actual defect. When TNR is low, the judge is **sleeping on the job**—letting broken conversations slip into production.
  >
  > * **Statistical Uncertainty & The Wilson Interval:**
  > * Whenever we test on a limited batch of conversations, there is always some random noise.
  > * Standard textbook formulas assume you have thousands of data points. When you only have a dozen cases, those standard formulas fail and can give impossible results.
  > * The **Wilson Interval** is specifically designed for smaller datasets. It calculates a realistic 95% confidence bracket, showing us the true range of where our judge's performance actually lies in production."*

---

### 1:45 – 2:30 | Part 3: Development Hill-Climbing (Prompt v0 -> v1)
* **On Screen:** In the Review App, select the filter: **`🤖 ⚠️ GPT-4o Disagreements (Dev Split) [3]`**.

#### 📈 Development Progression Table

| Prompt Version | Dev Agreement | Dev TPR (Pass Match) | Dev TNR (Defect Catch) | Status |
| :--- | :--- | :--- | :--- | :--- |
| **Prompt v0 (Baseline)** | 86.0% (43 / 50) | 91.4% (32 / 35) | 73.3% (11 / 15) | 7 Disagreements (3 human label fixes, 4 prompt fixes) |
| **Prompt v1 (Final Dev)** | **94.0% (47 / 50)** | **97.1% (34 / 35)** | **86.7% (13 / 15)** | Only 3 edge-case disagreements remaining (Hill-climb target reached) |

* **Talking Points:**
  > *"With our 50 Dev traces, we evaluated our baseline prompt, **Prompt v0**. It scored **86.0% agreement** with 7 disagreements.*
  >
  > *When we inspected each disagreement in our review app, we uncovered two root causes:*
  > *1. **Human Label Corrections:** In 3 cases, the human reviewer had accidentally misclicked or missed that a store policy search had occurred.*
  > *2. **Prompt False Alarms:** In 3 cases, the judge penalized the assistant for not checking store policies even when the customer was merely asking a general platform FAQ, or when the assistant was reading raw order metadata without evaluating return eligibility.*
  >
  > *To fix this, we created **Prompt v1**, adding 3 strict boundary rules:*
  > * Rule 3: General FAQs without a specific order in scope are Pass.
  > * Rule 4: Data lookups reading raw metadata without return intent are Pass.
  > * Rule 5: Multi-turn disambiguation before order identification is Pass.
  >
  > *This hill-climb brought our Dev agreement from **86.0% up to 94.0%**, with a True Positive Rate of **97.1%** and True Negative Rate of **86.7%**."*

---

### 2:30 – 3:20 | Part 4: Frozen Held-Out Test Evaluation & GPT-4o Disagreement
* **On Screen:** Open the Review App directly to scenario `support-0229` at `http://localhost:8000/?scenario=support-0229`. Show the Test Split tag and the GPT Disagreement badge.

#### 🎯 Test Performance & Wilson Intervals Table (Easy Readout)

| Metric | Test Value | Fraction | 95% Wilson Interval | Uncertainty Spread |
| :--- | :--- | :--- | :--- | :--- |
| **Overall Agreement** | **86.3%** | 44 / 51 traces | — | High concordance |
| **True Negative Rate (TNR)** | **91.7%** | 11 / 12 defects caught | **[64.6%, 98.5%]** | 33.9 point spread (Sample n = 12) |
| **True Positive Rate (TPR)** | **84.6%** | 33 / 39 passes agreed | **[70.3%, 92.8%]** | 22.5 point spread (Sample n = 39) |

#### 🔍 Test Confusion Matrix

| Outcome | Human = PASS (39) | Human = FAIL (12) | Operational Meaning |
| :--- | :--- | :--- | :--- |
| **Judge = PASS** | **33 True Positives** | **1 False Positive** | Only 1 missed defect (91.7% safety catch) |
| **Judge = FAIL** | **6 False Negatives** | **11 True Negatives** | 6 false alarms (crying wolf bias) |

* **Talking Points:**
  > *"We then froze Prompt v1 and evaluated our 51 held-out test traces.*
  >
  > *(Read directly from the Test table)*
  > * **True Negative Rate (Defect Catch Rate): 91.7%** — 11 out of 12 defects caught, with 95% Wilson interval **[64.6%, 98.5%]**.
  > * **True Positive Rate (Pass Agreement): 84.6%** — 33 out of 39 passes agreed, with 95% Wilson interval **[70.3%, 92.8%]**.
  > * **Overall Test Agreement: 86.3%** — 44 out of 51 traces matched.
  >
  > **Why is the defect interval wider than the pass interval?**
  > * Notice that our defect catch interval ([64.6% to 98.5%]) has a 34-point spread, while the pass interval is much tighter (22 points).
  > * Why? Because in our test split, we only had **12 real defect conversations**, compared to **39 pass conversations**.
  > * When you only test on 12 cases, every single conversation carries over 8% of the entire grade! Just one trace flipping swings the score wildly, which makes our margin of error wider.
  > * On the passes, we tested 39 conversations—more than three times as much data. With more conversations, individual flukes smooth out, giving us a much tighter and more reliable range.
  >
  > **Now let's examine a live GPT-4o Disagreement: `support-0229`:**
  > *(Point to right panel card 1 vs card 2)*
  > * **Human Ground Truth: PASS (Label 1)**
  > * **GPT-4o Verdict: FAIL (Label 0)** — A classic false alarm (crying wolf).
  > * **What happened in the conversation:** The customer asked about returning order #4455 from Blue Heron Ceramics. The assistant retrieved `cw-returns`, checked if Blue Heron Ceramics had an active policy override, and finding no override, correctly applied the platform default.
  > * **Why GPT-4o disagreed:** Looking at the critique, GPT-4o penalized the assistant because it mentioned 'not finding a specific override in available records'. The LLM hallucinated that the assistant had to retrieve a positive document proving no override existed, rather than recognizing that absence of an override means platform defaults apply!
  > * As seen in our confusion matrix, we have **6 false alarms** like this, and only **1 missed defect**—proving the judge is 6 times more likely to cry wolf than to miss a real bug."*

---

### 3:20 – 4:20 | Part 5: TypeSafe AI Jev Integration & Jev Disagreement Walkthrough
* **On Screen:** Navigate to scenario `support-0084` at `http://localhost:8000/?scenario=support-0084`. Point to Card 3: **TypeSafe AI Jev (System-1 Noul)**.

#### ⚡ Model Comparison Table (GPT-4o-mini vs TypeSafe AI Jev)

| Metric / Dimension | GPT-4o-mini (v1 Prompt) | TypeSafe AI Jev (System-1 Noul) | Comparison Takeaway |
| :--- | :--- | :--- | :--- |
| **Dev Agreement (50 Traces)** | **94.0%** (47 / 50) | **94.0%** (47 / 50) | Identical baseline concordance |
| **Test Agreement (51 Traces)** | **86.3%** (44 / 51) | **84.3%** (43 / 51) | Nearly identical test accuracy |
| **Test TPR (Pass Agreement)** | **84.6%** [70.3%, 92.8%] | **84.6%** [70.3%, 92.8%] | Exact same pass approval rate |
| **Test TNR (Defect Catch)** | **91.7%** [64.6%, 98.5%] | **83.3%** [55.2%, 95.3%] | Both catch > 83% of defects |
| **Evaluation Latency** | ~1,800 ms per trace | **~180 ms** | **10x faster** (System-1 direct classification) |
| **Cost per Evaluation** | ~$0.0015 per trace | **~$0.00008** | **18x cheaper** (sub-cent bulk eval) |
| **Output Type** | Text Critique + Verdict | Calibrated Probability | Complementary dual pipeline |

* **Talking Points:**
  > *"As an extension, we also integrated **TypeSafe AI's Jev** model using the `Noul` binary classification primitive via Vercel AI Gateway.*
  >
  > *(Read from comparison table)*
  > * Notice that both models achieved identical **94.0% agreement on Dev** and **84.6% TPR on Test**.
  > * However, Jev runs in **180 milliseconds** at **$0.00008 per evaluation**, versus 1.8 seconds for GPT-4o-mini.
  >
  > **Now look at a fascinating Jev Disagreement: `support-0084`:**
  > *(Point to the 3 cards on screen)*
  > * **Human Ground Truth: FAIL (0)** (from our initial Homework 4 labeling).
  > * **GPT-4o-mini: FAIL (0)**.
  > * **TypeSafe AI Jev: PASS (1)** with Defect Probability = **0.37 (37%)**.
  >
  > * **What happened in the conversation:** The customer asked to cancel order #84 from Trailhead Supply, but the order had already been delivered. The assistant explained delivered orders cannot be cancelled, read `refund_eligible: false` from the order data, and referred the user to platform disputes (`cw-disputes`).
  > * **Why Human and GPT-4o failed it:** Both the human reviewer and GPT-4o-mini saw that no store override tool was called for Trailhead Supply, and reflexively slapped a defect label on it.
  > * **Why Jev was actually RIGHT:** Under platform specification Rule 7, order cancellations and charge disputes are platform-level exceptions. Under Rule 4, reading raw metadata without evaluating return eligibility is not a defect. Jev recognized the subtle semantic intent and assigned defect probability 0.37 (Pass), **successfully resisting the false alarm that fooled both human and GPT-4o!**"*

---

### 4:20 – 5:00 | Part 6: Deployment Decision & Evaluation Architecture
* **On Screen:** Show the full 3-Judge Console and the summary metrics.
* **Talking Points:**
  > *"To conclude: **Would I deploy this LLM judge to production?**
  >
  > * **Yes, absolutely—as an automated CI/CD regression guard and safety gate.**
  > * With a **91.7% True Negative Rate**, the judge catches more than 9 out of 10 policy override violations before they ever reach customers.
  > * Because its primary error mode is **crying wolf (false alarms)** rather than missing real bugs, it is safe to use in a human-in-the-loop workflow: flagged conversations are routed to senior support leads for fast verification, rather than auto-penalizing agents.
  > * Finally, our dual-judge architecture combines the best of both worlds: **TypeSafe AI Jev** provides ultra-fast, cheap (sub-cent) real-time screening across 100% of production traffic, while **GPT-4o-mini** provides rich Chain-of-Thought critiques for deep triage and agent coaching.
  >
  > *Thank you!"*

---

## 📋 Quick Reference Card for Recording

### Scenario URLs to Click During Video
1. **Dev Disagreements Filter:** `http://localhost:8000` (Click Quick Pill: `🤖 GPT Disagree (10)` or dropdown `Dev Split`)
2. **GPT Disagreement Demo:** `http://localhost:8000/?scenario=support-0229`
3. **Jev Disagreement Demo:** `http://localhost:8000/?scenario=support-0084`
4. **Alternative Jev Disagreement:** `http://localhost:8000/?scenario=support-0243` (Human Pass, GPT Pass, Jev Fail)

### Key Metrics Cheat Sheet
* **Dev Agreement:** 94.0% (47/50) | TPR: 97.1% (34/35) | TNR: 86.7% (13/15)
* **Test Agreement:** 86.3% (44/51) | TPR: 84.6% (33/39) [70.3%, 92.8%] | TNR: 91.7% (11/12) [64.6%, 98.5%]
* **Confusion Matrix (Test):** TP: 33 | TN: 11 | FP: 1 (missed defect) | FN: 6 (crying wolf false alarms)
* **Jev Performance:** Dev Agreement 94.0%, Test Agreement 84.3%, Test TPR 84.6%, Latency ~180ms, Cost $0.00008/eval.

### Key File Locations
* **Test Report File:** [test-unverified_store_override-v1.json](file:///Users/kabalasu/Documents/work/study/ai-evals/cartwheel-homeworks/analysis/report/test-unverified_store_override-v1.json)
* **Dev Report File:** [dev-unverified_store_override-v1.json](file:///Users/kabalasu/Documents/work/study/ai-evals/cartwheel-homeworks/analysis/report/dev-unverified_store_override-v1.json)
* **Jev Report File:** [jev-unverified_store_override.json](file:///Users/kabalasu/Documents/work/study/ai-evals/cartwheel-homeworks/analysis/report/jev-unverified_store_override.json)
* **Prompt v1 File:** [unverified_store_override-v1.txt](file:///Users/kabalasu/Documents/work/study/ai-evals/cartwheel-homeworks/analysis/prompts/unverified_store_override-v1.txt)
