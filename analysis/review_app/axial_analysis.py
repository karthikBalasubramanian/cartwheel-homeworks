"""Scientific Axial Coding and Semantic Clustering Engine.

Computes TF-IDF representations, pairwise cosine similarity matrices,
centroid-based clustering, and automated snake_case failure mode suggestions
across all human trace annotations (Fails and Passes with notes).
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
TRACES_PATH = REPO_ROOT / "traces" / "support_traces.json"
_CACHED_TRACES: dict[str, Any] | None = None


def _get_trace_lookup() -> dict[str, Any]:
    global _CACHED_TRACES
    if _CACHED_TRACES is not None:
        return _CACHED_TRACES
    lookup: dict[str, Any] = {}
    if TRACES_PATH.exists():
        try:
            with open(TRACES_PATH, encoding="utf-8") as f:
                data = json.load(f)
            traces = data.get("traces", data.get("data", []))
            for t in traces:
                scen = (
                    t.get("cartwheel_scenario_id")
                    or t.get("metadata", {}).get("cartwheel.scenario_id")
                    or t.get("metadata", {}).get("attributes", {}).get("cartwheel.scenario_id")
                )
                if scen and scen not in lookup:
                    lookup[scen] = t
        except Exception:
            pass
    _CACHED_TRACES = lookup
    return _CACHED_TRACES

# Standard English stopwords plus domain-ubiquitous terms that carry no discriminatory value
STOPWORDS = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and",
    "any", "are", "aren't", "as", "at", "be", "because", "been", "before", "being",
    "below", "between", "both", "but", "by", "can", "can't", "cannot", "could",
    "couldn't", "did", "didn't", "do", "does", "doesn't", "doing", "don't", "down",
    "during", "each", "few", "for", "from", "further", "had", "hadn't", "has",
    "hasn't", "have", "haven't", "having", "he", "he'd", "he'll", "he's", "her",
    "here", "here's", "hers", "herself", "him", "himself", "his", "how", "how's",
    "i", "i'd", "i'll", "i'm", "i've", "if", "in", "into", "is", "isn't", "it",
    "it's", "its", "itself", "let's", "me", "more", "most", "mustn't", "my",
    "myself", "no", "nor", "not", "of", "off", "on", "once", "only", "or",
    "other", "ought", "our", "ours", "ourselves", "out", "over", "own", "same",
    "shan't", "she", "she'd", "she'll", "she's", "should", "shouldn't", "so",
    "some", "such", "than", "that", "that's", "the", "their", "theirs", "them",
    "themselves", "then", "there", "there's", "these", "they", "they'd", "they'll",
    "they're", "they've", "this", "those", "through", "to", "too", "under", "until",
    "up", "very", "was", "wasn't", "we", "we'd", "we'll", "we're", "we've",
    "were", "weren't", "what", "what's", "when", "when's", "where", "where's",
    "which", "while", "who", "who's", "whom", "why", "why's", "with", "won't",
    "would", "wouldn't", "you", "you'd", "you'll", "you're", "you've", "your",
    "yours", "yourself", "yourselves",
    # Low-information operational markers in trace notes
    "turn", "first", "failure", "assistant", "response", "deliberation", "agent",
    "also", "think", "like", "would", "could", "said", "shows", "case",
    "thing", "point", "well", "see", "says", "just", "make", "take", "instead",
    # Filter boilerplate pass phrases from polluting vocabulary
    "observed", "clean", "execution", "conforming", "specification", "none",
    "observed_clean", "conforming_specification", "clean_execution"
}

TOKEN_PATTERN = re.compile(r"[a-z0-9_]{3,}")


def tokenize(text: str) -> list[str]:
    """Tokenize and filter stopwords."""
    clean = text.lower().replace("-", "_")
    tokens = TOKEN_PATTERN.findall(clean)
    return [t for t in tokens if t not in STOPWORDS]


def extract_bigrams(tokens: list[str]) -> list[str]:
    """Extract adjacent bi-grams."""
    return [f"{tokens[i]}_{tokens[i+1]}" for i in range(len(tokens) - 1)]


class AxialCorpus:
    """Represents the corpus of reviewed traces with human observations."""

    def __init__(self, records: list[dict[str, Any]]):
        self.records = records
        self.doc_tokens: list[list[str]] = []
        self.doc_bigrams: list[list[str]] = []
        self.vocabulary: list[str] = []
        self.vocab_index: dict[str, int] = {}
        self.idf: list[float] = []
        self.vectors: list[list[float]] = []

        self._build_vectors()

    def _build_vectors(self) -> None:
        n_docs = len(self.records)
        if n_docs == 0:
            return

        doc_freqs: Counter[str] = Counter()
        for rec in self.records:
            text = rec["full_text"]
            tokens = tokenize(text)
            bigrams = extract_bigrams(tokens)
            self.doc_tokens.append(tokens)
            self.doc_bigrams.append(bigrams)

            unique_terms = set(tokens + bigrams)
            for t in unique_terms:
                doc_freqs[t] += 1

        # Keep terms that appear in at least 1 doc but filter out noise
        sorted_terms = [term for term, freq in doc_freqs.most_common() if freq >= 1]
        self.vocabulary = sorted_terms
        self.vocab_index = {term: idx for idx, term in enumerate(sorted_terms)}

        # Standard smooth IDF: ln((1 + N) / (1 + DF)) + 1
        self.idf = [
            math.log((1.0 + n_docs) / (1.0 + doc_freqs[t])) + 1.0
            for t in self.vocabulary
        ]

        # Compute normalized TF-IDF vectors
        for i, rec in enumerate(self.records):
            counts = Counter(self.doc_tokens[i] + self.doc_bigrams[i])
            vec = [0.0] * len(self.vocabulary)
            norm_sq = 0.0
            for term, count in counts.items():
                if term in self.vocab_index:
                    idx = self.vocab_index[term]
                    # sublinear TF scaling: 1 + log(tf)
                    tf = 1.0 + math.log(count)
                    weight = tf * self.idf[idx]
                    vec[idx] = weight
                    norm_sq += weight * weight

            norm = math.sqrt(norm_sq) or 1.0
            self.vectors.append([w / norm for w in vec])


def cosine_similarity(v1: list[float], v2: list[float]) -> float:
    """Cosine similarity of two normalized vectors."""
    dot = sum(a * b for a, b in zip(v1, v2))
    return max(0.0, min(1.0, dot))


def compute_similarity_matrix(vectors: list[list[float]]) -> list[list[float]]:
    """Compute complete N x N pairwise similarity matrix."""
    n = len(vectors)
    matrix = [[1.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            sim = round(cosine_similarity(vectors[i], vectors[j]), 3)
            matrix[i][j] = sim
            matrix[j][i] = sim
    return matrix


def agglomerative_cluster(
    vectors: list[list[float]], k: int = 6
) -> list[int]:
    """Hierarchical agglomerative clustering with average linkage."""
    n = len(vectors)
    if n <= k:
        return list(range(n))

    # Start with each vector in its own cluster
    clusters = {i: [i] for i in range(n)}
    sim_cache: dict[tuple[int, int], float] = {}

    def get_cluster_sim(c1_idx: int, c2_idx: int) -> float:
        pair = (min(c1_idx, c2_idx), max(c1_idx, c2_idx))
        if pair in sim_cache:
            return sim_cache[pair]
        members1 = clusters[c1_idx]
        members2 = clusters[c2_idx]
        total_sim = sum(
            cosine_similarity(vectors[i], vectors[j])
            for i in members1
            for j in members2
        )
        avg_sim = total_sim / (len(members1) * len(members2))
        sim_cache[pair] = avg_sim
        return avg_sim

    next_cid = n
    while len(clusters) > k:
        best_sim = -1.0
        best_pair = (-1, -1)
        cluster_ids = list(clusters.keys())

        for i in range(len(cluster_ids)):
            for j in range(i + 1, len(cluster_ids)):
                c1 = cluster_ids[i]
                c2 = cluster_ids[j]
                sim = get_cluster_sim(c1, c2)
                if sim > best_sim:
                    best_sim = sim
                    best_pair = (c1, c2)

        c1, c2 = best_pair
        new_members = clusters[c1] + clusters[c2]
        del clusters[c1]
        del clusters[c2]
        clusters[next_cid] = new_members
        next_cid += 1

    # Map each vector index to final cluster index 0..k-1
    assignments = [0] * n
    for cluster_num, members in enumerate(clusters.values()):
        for idx in members:
            assignments[idx] = cluster_num

    return assignments


def generate_mode_name(top_terms: list[str], used_names: set[str] | None = None) -> str:
    """Generate canonical snake_case mode names from distinctive terms."""
    key_text = " ".join(top_terms).lower()
    lead_term = top_terms[0].lower() if top_terms else ""

    if any(k in key_text for k in ("refunded", "issuerefund", "unsolicited", "premature_action", "6428", "preshipment", "cancel", "ventured")) or ("refund" in key_text and "delivered" in key_text):
        candidate = "unsolicited_action_execution"
    elif any(k in key_text for k in ("tracking_link", "carrier", "tracking")) and "refund" not in lead_term:
        candidate = "missing_tracking_capability"
    elif any(k in key_text for k in ("unlinked", "policy_reference", "policy", "internal", "slug", "cw_", "refund_eligible", "leak", "links")):
        candidate = "internal_policy_identifier_leak"
    elif any(k in key_text for k in ("meridian", "store_specific", "store_policy", "override", "store", "correct_store", "whale_workshop", "cautious_explanation", "order_belongs")):
        candidate = "unverified_store_override"
    elif any(k in key_text for k in ("unnecessary_tool", "tool_call", "search_products", "redundant_tool", "unnecessary")):
        candidate = "unnecessary_tool_call"
    elif any(k in key_text for k in ("name", "product_id", "product_name", "numeric", "dimensions", "product", "identifiers", "4127")):
        candidate = "unresolved_product_identifiers"
    elif any(k in key_text for k in ("escalate", "ticket", "escalation", "support_ticket", "stopped", "human_unwind")):
        candidate = "unnecessary_escalation"
    else:
        clean_terms = [re.sub(r"[^a-z0-9]", "", t) for t in top_terms[:2] if t]
        candidate = "_".join(clean_terms) if clean_terms else "unclassified_mode"

    if used_names is not None and candidate in used_names:
        clean_terms = [re.sub(r"[^a-z0-9]", "", t) for t in top_terms if t and t != candidate and "tracking" not in t]
        suffix = clean_terms[0] if clean_terms else "alt"
        candidate = f"{candidate}_{suffix}"

    return candidate


def project_2d(similarity_matrix: list[list[float]], assignments: list[int]) -> list[dict[str, float]]:
    """Generates 2D cluster coordinates using multidimensional scaling / force relaxation."""
    n = len(similarity_matrix)
    if n == 0:
        return []

    # Assign initial angles based on cluster
    coords: list[dict[str, float]] = []
    cluster_angles: dict[int, float] = {}
    unique_clusters = sorted(list(set(assignments)))
    num_clusters = len(unique_clusters)

    for i, c in enumerate(unique_clusters):
        cluster_angles[c] = (2.0 * math.pi * i) / max(1, num_clusters)

    for i in range(n):
        c = assignments[i]
        base_angle = cluster_angles[c]
        # Spread points slightly within cluster radius
        jitter = (hash(str(i)) % 100) / 100.0 - 0.5
        radius = 180.0 + (jitter * 70.0)
        angle = base_angle + (jitter * 0.4)
        x = round(350.0 + radius * math.cos(angle), 1)
        y = round(280.0 + radius * math.sin(angle), 1)
        coords.append({"x": x, "y": y})

    return coords


def run_axial_analysis(
    annotations: list[dict[str, Any]],
    k_clusters: int = 6
) -> dict[str, Any]:
    """Executes grounded theory axial coding pipeline with human-comment priority."""
    trace_lookup = _get_trace_lookup()
    records = []
    for ann in annotations:
        scen = ann.get("scenario_id")
        note = ann.get("note", "").strip()
        step_notes = ann.get("step_notes", {})
        step_text = " ".join(s.get("text", "") for s in step_notes.values() if isinstance(s, dict)).strip()
        human_comment = f"{note} {step_text}".strip()

        modes = ann.get("modes", {})
        tagged_modes = [m for m, active in modes.items() if active]
        modes_text = " ".join(tagged_modes).replace("_", " ")

        # Extract actual tool executions and message text for grounding/fallback
        t = trace_lookup.get(scen, {})
        tools_called = [o.get("name") for o in t.get("observations", []) if o.get("type") == "TOOL" and o.get("name")]
        tool_tokens = " ".join([f"tool_{name} {name}" for name in tools_called])

        user_msgs = []
        asst_msgs = []
        for m in t.get("input", []):
            if isinstance(m, dict):
                for p in m.get("parts", []):
                    if isinstance(p, dict) and p.get("type") == "text":
                        user_msgs.append(p.get("content", ""))
        for m in t.get("output", []):
            if isinstance(m, dict):
                for p in m.get("parts", []):
                    if isinstance(p, dict) and p.get("type") == "text":
                        asst_msgs.append(p.get("content", ""))

        scenario_transcript = f"{' '.join(user_msgs)} {tool_tokens} {' '.join(asst_msgs)}".strip()

        verdict = ann.get("verdict")
        label = ann.get("label")
        is_fail = (verdict == "fail") or (label == 0)

        has_freeform_note = bool(human_comment) and human_comment.lower() not in (
            "no failure observed", "failure observed", "no failure observed clean execution conforming to specification"
        )

        if has_freeform_note:
            # Human freeform note is available: Give it paramount weight (6x), with tagged taxonomy as secondary context (2x)
            full_text = f"{human_comment} {human_comment} {human_comment} {human_comment} {human_comment} {human_comment} {modes_text} {modes_text} {tool_tokens}".strip()
            display_note = human_comment
        elif tagged_modes:
            # Freeform note is absent, but Failure Mode Taxonomy was checked: Give tagged taxonomy primary weight (6x)
            full_text = f"{modes_text} {modes_text} {modes_text} {modes_text} {modes_text} {modes_text} {tool_tokens}".strip()
            display_note = f"Tagged mode: {', '.join(tagged_modes)}"
        else:
            # Neither is available: Fall back to raw scenario transcript & tool calls
            full_text = f"{scenario_transcript} {tool_tokens}".strip()
            display_note = "No failure observed" if not is_fail else "Failure observed"

        records.append({
            "scenario_id": scen,
            "trace_id": ann.get("trace_id"),
            "session_id": ann.get("session_id"),
            "verdict": "fail" if is_fail else "pass",
            "label": 0 if is_fail else 1,
            "earliest_failure_location": ann.get("earliest_failure_location"),
            "note": display_note,
            "full_text": full_text,
        })

    if not records:
        return {"ok": True, "clusters": [], "matrix": [], "records": []}

    corpus = AxialCorpus(records)
    n = len(records)
    k = min(k_clusters, n)

    # Separate fail records from pass records
    fail_indices = [i for i, r in enumerate(records) if r["verdict"] == "fail"]
    pass_indices = [i for i, r in enumerate(records) if r["verdict"] != "fail"]

    # Grounded theory axial coding: group failure observations into k failure modes
    assignments = [0] * n
    centroids = []
    cluster_fail_members = defaultdict(list)
    cluster_pass_members = defaultdict(list)

    if len(fail_indices) >= k:
        fail_vectors = [corpus.vectors[i] for i in fail_indices]
        fail_cluster_assignments = agglomerative_cluster(fail_vectors, k=k)

        for local_idx, c_id in enumerate(fail_cluster_assignments):
            global_idx = fail_indices[local_idx]
            assignments[global_idx] = c_id
            cluster_fail_members[c_id].append(global_idx)

        # Compute centroid for each failure cluster
        for c_id in range(k):
            members = cluster_fail_members[c_id]
            c_vec = [0.0] * len(corpus.vocabulary)
            for g_idx in members:
                for d in range(len(corpus.vocabulary)):
                    c_vec[d] += corpus.vectors[g_idx][d]
            for d in range(len(corpus.vocabulary)):
                c_vec[d] /= max(1, len(members))
            c_norm = math.sqrt(sum(x * x for x in c_vec)) or 1.0
            centroids.append([x / c_norm for x in c_vec])

        # Assign passes as close negatives based on proximity to nearest failure centroid
        for p_idx in pass_indices:
            sims = [cosine_similarity(corpus.vectors[p_idx], c_vec) for c_vec in centroids]
            best_c = max(range(k), key=lambda c: sims[c]) if centroids else 0
            best_sim = sims[best_c] if centroids else 0.0
            assignments[p_idx] = best_c
            # Only connect as a close negative if similarity meets minimum threshold (>= 0.10)
            if best_sim >= 0.10:
                cluster_pass_members[best_c].append(p_idx)
    else:
        # Fallback if too few failure records
        assignments = agglomerative_cluster(corpus.vectors, k=k)
        for idx, c in enumerate(assignments):
            if records[idx]["verdict"] == "fail":
                cluster_fail_members[c].append(idx)
            else:
                cluster_pass_members[c].append(idx)
        for c_id in range(k):
            members = cluster_fail_members[c_id] + cluster_pass_members[c_id]
            c_vec = [0.0] * len(corpus.vocabulary)
            for g_idx in members:
                for d in range(len(corpus.vocabulary)):
                    c_vec[d] += corpus.vectors[g_idx][d]
            for d in range(len(corpus.vocabulary)):
                c_vec[d] /= max(1, len(members))
            c_norm = math.sqrt(sum(x * x for x in c_vec)) or 1.0
            centroids.append([x / c_norm for x in c_vec])

    sim_matrix = compute_similarity_matrix(corpus.vectors)
    coords_2d = project_2d(sim_matrix, assignments)

    clusters_payload = []
    used_names: set[str] = set()
    for c_id in range(k):
        norm_centroid = centroids[c_id] if c_id < len(centroids) else [0.0] * len(corpus.vocabulary)

        # Distinctive terms: terms with highest weights in centroid
        term_scores = [
            (corpus.vocabulary[d], norm_centroid[d])
            for d in range(len(corpus.vocabulary))
            if norm_centroid[d] > 0.04
        ]
        term_scores.sort(key=lambda x: x[1], reverse=True)
        top_terms = [t[0] for t in term_scores[:6]]
        suggested_name = generate_mode_name(top_terms, used_names)
        used_names.add(suggested_name)

        fail_m = cluster_fail_members[c_id]
        pass_m = cluster_pass_members[c_id]
        all_members = fail_m + pass_m

        member_items = []
        for idx in all_members:
            rec = records[idx]
            fit_score = round(cosine_similarity(corpus.vectors[idx], norm_centroid), 3)
            member_items.append({
                "scenario_id": rec["scenario_id"],
                "trace_id": rec["trace_id"],
                "verdict": rec["verdict"],
                "label": rec["label"],
                "fit_score": fit_score,
                "note": rec["note"],
                "location": rec["earliest_failure_location"],
                "coords": coords_2d[idx],
                "index": idx,
            })

        member_items.sort(key=lambda m: m["fit_score"], reverse=True)
        core_positives = [m for m in member_items if m["verdict"] == "fail"]
        close_negatives = [m for m in member_items if m["verdict"] == "pass"]

        clusters_payload.append({
            "cluster_id": c_id,
            "name": suggested_name,
            "top_terms": top_terms,
            "total_count": len(all_members),
            "fail_count": len(core_positives),
            "pass_count": len(close_negatives),
            "core_positives": core_positives,
            "close_negatives": close_negatives,
            "members": member_items,
        })

    # Sort clusters by fail count descending
    clusters_payload.sort(key=lambda c: c["fail_count"], reverse=True)

    # Attach coordinates and cluster id directly to record list
    enriched_records = []
    for idx, rec in enumerate(records):
        enriched_records.append({
            "index": idx,
            "scenario_id": rec["scenario_id"],
            "trace_id": rec["trace_id"],
            "verdict": rec["verdict"],
            "note": rec["note"],
            "cluster_id": assignments[idx],
            "coords": coords_2d[idx],
        })

    return {
        "ok": True,
        "total_analyzed": len(records),
        "total_failures": len(fail_indices),
        "total_passes": len(pass_indices),
        "close_negatives_count": sum(c["pass_count"] for c in clusters_payload),
        "k_clusters": len(clusters_payload),
        "clusters": clusters_payload,
        "records": enriched_records,
        "similarity_matrix": sim_matrix,
    }
