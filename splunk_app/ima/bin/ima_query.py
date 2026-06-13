#!/usr/bin/env python
"""Custom search command: | imaquery question="what do we know about X?"

Splunk's SPL parser rejects underscores in command names, so the stanza in
commands.conf is `imaquery` even though this file is named `ima_query.py`.

Usage in Splunk search bar:
  | imaquery question="finance Monday"
  | imaquery question="executive traveling" semantic=true top_k=3
"""
from __future__ import annotations

import os
import sys

_here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_here, "lib"))   # vendored splunklib
sys.path.insert(0, _here)                         # sibling _ima_common

from splunklib.searchcommands import (
    Configuration,
    GeneratingCommand,
    Option,
    dispatch,
    validators,
)

from _ima_common import KV_KNOWLEDGE, cosine_similarity, embed, kv_query


def _row_text(r: dict) -> str:
    return " ".join(str(r.get(k, "")) for k in ("topic", "summary", "tags"))


@Configuration()
class ImaQueryCommand(GeneratingCommand):
    question = Option(require=True, validate=validators.Match("question", r".+"))
    semantic = Option(require=False, default="true")
    top_k = Option(require=False, default="5")
    min_sim = Option(require=False, default="0.4")

    def generate(self):
        rows = kv_query(self.service, KV_KNOWLEDGE)
        want_semantic = str(self.semantic).strip().lower() in {"true", "1", "yes"}
        top_k = int(self.top_k)
        min_sim = float(self.min_sim)

        scored = []
        method = "substring"

        if want_semantic:
            q_emb = embed(self.question)
            if q_emb is not None:
                method = "semantic"
                for r in rows:
                    r_emb = embed(_row_text(r))
                    if r_emb is None:
                        continue
                    sim = cosine_similarity(q_emb, r_emb)
                    if sim >= min_sim:
                        scored.append((sim, r))

        if not scored:
            needle = self.question.lower()
            scored = [(1.0, r) for r in rows if needle in _row_text(r).lower()]

        scored.sort(key=lambda t: (t[0], float(t[1].get("confidence", 0) or 0)), reverse=True)
        for sim, r in scored[:top_k]:
            yield {
                "_time": r.get("updated_at", ""),
                "similarity": round(sim, 3),
                "topic": r.get("topic", ""),
                "summary": r.get("summary", ""),
                "evidence_count": r.get("evidence_count", 0),
                "confidence": r.get("confidence", 0),
                "tags": r.get("tags", ""),
                "search_method": method,
            }


dispatch(ImaQueryCommand, sys.argv, sys.stdin, sys.stdout, __name__)
