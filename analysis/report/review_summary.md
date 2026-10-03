# Cartwheel Human Trace Review Summary (Homework 4)

## 1. Executive Summary & Sample Composition
Across four structured sampling batches conforming to grounded theory methodology (`homework/module-2/hw4.md`), **100 distinct Cartwheel support traces** were reviewed using the custom web review interface (`analysis/review_app/`):

- **Batch 1 (Discovery):** 30 traces (15 diversity/cluster representatives + 15 uniform random samples) establishing preliminary open coding notes.
- **Batch 2 (Stratified):** 30 traces stratified across Cartwheel product user roles (Shopper, Merchant, Support Staff) to discover role-boundary defects.
- **Batch 3 (Targeted Depth Search):** 25 traces retrieved via semantic similarity against emerging axial failure modes and close negatives.
- **Batch 4 (Holdout Stability Check):** 15 uniformly sampled traces from the unreviewed candidate pool to evaluate theoretical saturation.

**Overall Sample Outcome:**
- **Pass (Conforming execution):** 59 traces (59.0%)
- **Fail (Defect / Failure present):** 40 traces (40.0%)
- **Deferred:** 1 trace (1.0%)

---

## 2. Theoretical Saturation Assessment (Batch 4 Holdout)
In the final 15 uniform holdout traces (Batch 4):
- **Passes:** 8 traces (`support-0003`, `support-0024`, `support-0040`, `support-0077`, `support-0122`, `support-0130`, `support-0208`, `support-0230`)
- **Failures:** 7 traces (`support-0150`, `support-0196`, `support-0206`, `support-0212`, `support-0213`, `support-0237`, `support-0238`)
- **New Consequential Failure Modes Observed:** **0**

Every failure in the final holdout batch mapped cleanly into previously identified categories (`unnecessary_tool_call`, `missing_tracking_capability`, `unverified_store_override`). This empirical convergence confirms **theoretical saturation**—reviewing further traces yields diminishing returns of novel failure modes.

---

## 3. The Final Failure Taxonomy (6 Modes)

| Mode Name | Evaluator Type | Confirmed Positives | Close Negatives | Sample Fraction | Requirement Source |
|---|---|---|---|---|---|
| `missing_tracking_capability` | `code` (URL / carrier regex) | 11 | 7 | 11.0% | SPEC-REVISION-1 (RESP-6) |
| `internal_policy_identifier_leak` | `code` (slug regex) | 11 | 8 | 11.0% | RESP-4 / RESP-5 |
| `unnecessary_tool_call` | `code` (trajectory analyzer) | 10 | 16 | 10.0% | TOOL-3 / TOOL-5 |
| `unresolved_product_identifiers` | `judge` (LLM evaluator) | 7 | 5 | 7.0% | RESP-5 / TOOL-3 |
| `unsolicited_action_execution` | `judge` (LLM evaluator) | 4 | 5 | 4.0% | RESP-2 / PURPOSE-1 |
| `unverified_store_override` | `judge` (LLM evaluator) | 6 | 7 | 6.0% | AUTH-1 / TOOL-2 |

---

### 3.1 Semantic Clustering Methodology (Centroid-Based Axial Clustering)

To transition rigorously from qualitative open coding (Batches 1 & 2) to structured axial failure modes, we implemented a grounded theory semantic clustering engine (`analysis/review_app/axial_analysis.py`):

1. **Hierarchical Document Weighting (Human Primacy):**
   - In grounded theory, human evaluative judgment is the primary signal. Document representations are constructed using a hierarchical tiered weighting scheme:
     - **Primary Tier (6x weight):** When freeform reviewer notes (`note` + `step_notes`) are present, they are repeated with 6x weight. Checkbox taxonomy selections receive 2x secondary context, and invoked tool tokens (`tool_<name>`) are appended.
     - **Secondary Tier (6x tagged weight):** If freeform notes are blank, any marked Failure Mode Taxonomy checkboxes receive 6x weight alongside tool calls.
     - **Fallback Tier (1x weight):** If neither is present, the model falls back to the raw scenario transcript (user messages, tool observations, assistant output).

2. **Feature Extraction (TF-IDF with Sublinear Scaling & Bigrams):**
   - **Vocabulary & Stopwords:** Tokenized into unigrams and adjacent bigrams. English stopwords and low-information domain markers (`turn`, `assistant`, `response`, `observed_clean`, `conforming_specification`) are eliminated to prevent artifactual clustering.
   - **Smooth Inverse Document Frequency (IDF):**
     $$\text{IDF}(t) = \ln\left(\frac{1 + N}{1 + \text{DF}(t)}\right) + 1$$
   - **Sublinear Term Frequency Scaling:** $\text{TF}(t, d) = 1 + \ln(\text{count}(t, d))$ for $\text{count} > 0$.
   - **Unit Hypersphere Projection ($L_2$ Normalization):** Each document vector is normalized ($||\mathbf{v}||_2 = 1.0$) such that cosine similarity is the inner product: $\text{sim}(\mathbf{u}, \mathbf{v}) = \mathbf{u} \cdot \mathbf{v}$.

3. **Failure-Centric Clustering ($k=6$ Centroids):**
   - Rather than clustering passes and failures together (which creates spurious "conforming execution" clusters), clustering is performed **strictly on the 40 confirmed failure vectors**.
   - Hierarchical agglomerative clustering with average linkage merges failure vectors until exactly $k=6$ clusters remain.
   - For each cluster $\mathcal{C}_k$, a normalized centroid vector is computed:
     $$\mathbf{\mu}_k = \frac{\sum_{i \in \mathcal{C}_k} \mathbf{v}_i}{\left\|\sum_{i \in \mathcal{C}_k} \mathbf{v}_i\right\|_2}$$

4. **Close Negative Attachment (Thresholded Boundary Discovery):**
   - The 60 passing traces are compared against all 6 failure centroids: $\text{sim}(\mathbf{v}_p, \mathbf{\mu}_k) = \mathbf{v}_p \cdot \mathbf{\mu}_k$.
   - A threshold ($\text{sim} \ge 0.10$) ensures only passes that genuinely share vocabulary/tools with the failure mode (e.g. an order lookup that successfully provided tracking info) attach as **close negatives** (27 traces). Clean baseline passes lacking similarity remain unattached, preventing false associations (e.g. non-escalation passes like `support-0162`).

5. **Canonical Mode Generation & 2D Projection:**
   - Dominant terms with high weights in $\mathbf{\mu}_k$ dictate the canonical snake_case failure mode names.
   - Pairwise cosine similarities are projected into 2D cluster coordinates via force relaxation for interactive exploration in `/axial`.

---

## 4. Key Taxonomy Revision & The Lexical Split
A critical grounded theory insight emerged during Batch 4 regarding **`unnecessary_tool_call`**:
- **The Lexical Trap:** Initial statistical clustering (TF-IDF vectorization) grouped tool call traces (`support-0196`, `support-0197`, `support-0237`, `support-0238`) together with catalog description failures (`support-0139`, `support-0150`) under `unresolved_product_identifiers` because both contained the token `"product"` (e.g. `search_products` tool call versus product catalog ID formatting).
- **The Qualitative Split:** Per `hw4.md` guidelines, groups must be split when their engineering remediation requires distinct interventions. `unresolved_product_identifiers` requires catalog resolution in assistant output strings, whereas `unnecessary_tool_call` requires trajectory stop rules and prompt constraints on tool invocation. The mode was formally split and isolated.

---

## 5. Rejected Search Suggestions
During candidate depth retrieval, retrieval signals returned close negative examples that were explicitly inspected and rejected:
- **`support-0003` (for `missing_tracking_capability`):** Rejected because the order status was `placed` and not yet fulfilled by the carrier; tracking requirements only apply to `shipped` or `delivered` statuses.
- **`support-0145` (for `unnecessary_tool_call`):** Rejected because the `get_order` invocation was required to fetch missing customer order context.
- **`support-0222` (for `unverified_store_override`):** Rejected because the merchant had no registered override policy, making fallback to platform defaults correct.

---

## 6. Specification Revision
- **Revision Identifier:** `SPEC-REVISION-1`
- **Motivating Annotation:** `support-0004`, `support-0012`, `support-0029`
- **Specification Text Addition to `SPEC.md` Section 6:**
  > **RESP-6.** When an order status lookup returns `shipped` or `delivered`, the agent must provide carrier tracking details or explicit tracking guidance rather than merely confirming internal delivery records without external verification links.
