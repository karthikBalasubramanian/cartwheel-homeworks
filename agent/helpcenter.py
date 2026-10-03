"""Help-center corpus loading and BM25 retrieval. Instructor-provided.

Backs the `search_help_center` lecture tool and the `get_policy` homework
tool. The corpus is the markdown files in data/policies/, each with YAML
front matter carrying at least `policy_id`, `title`, and `audience`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml
# pyrefly: ignore [missing-import]
from rank_bm25 import BM25Okapi

from agent.config import policies_dir

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


@dataclass(frozen=True)
class PolicyDoc:
    policy_id: str
    title: str
    audience: str
    body: str
    path: Path


def load_policy_docs(directory: Path | None = None) -> list[PolicyDoc]:
    """Load and parse every policy doc, sorted by policy_id."""
    directory = directory or policies_dir()
    if not directory.exists():
        raise FileNotFoundError(
            f"{directory} does not exist. Run: uv run python -m seed.generate"
        )
    docs: list[PolicyDoc] = []
    for path in sorted(directory.glob("*.md")):
        text = path.read_text()
        _, raw_front, body = text.split("---", 2)
        front = yaml.safe_load(raw_front)
        docs.append(
            PolicyDoc(
                policy_id=front["policy_id"],
                title=front["title"],
                audience=front.get("audience", "all"),
                body=body.strip(),
                path=path,
            )
        )
    return sorted(docs, key=lambda d: d.policy_id)


class HelpCenterIndex:
    """BM25 index over the policy corpus (title + body)."""

    def __init__(self, docs: list[PolicyDoc]):
        self.docs = docs
        self._bm25 = BM25Okapi([_tokenize(f"{d.title} {d.body}") for d in docs])

    def search(self, query: str, k: int = 3) -> list[tuple[PolicyDoc, float]]:
        """Top-k docs by BM25 score, best first. Ties break by policy_id."""
        scores = self._bm25.get_scores(_tokenize(query))
        ranked = sorted(
            zip(self.docs, scores), key=lambda pair: (-pair[1], pair[0].policy_id)
        )
        return ranked[:k]


_INDEX_CACHE: dict[str, HelpCenterIndex] = {}


def get_index(directory: Path | None = None) -> HelpCenterIndex:
    """A cached index per corpus directory (the corpus is static at runtime)."""
    directory = directory or policies_dir()
    key = str(directory.resolve())
    if key not in _INDEX_CACHE:
        _INDEX_CACHE[key] = HelpCenterIndex(load_policy_docs(directory))
    return _INDEX_CACHE[key]
