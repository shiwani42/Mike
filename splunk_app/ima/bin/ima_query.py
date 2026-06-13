#!/usr/bin/env python
"""Custom search command: | ima_query question="what do we know about X?"

Generates rows from the institutional knowledge graph that match the question.
Usage in Splunk search bar:
  | ima_query question="finance Monday"
  | ima_query question="ciso travel"
"""
from __future__ import annotations

import sys

from splunklib.searchcommands import (
    Configuration,
    GeneratingCommand,
    Option,
    dispatch,
    validators,
)

from _ima_common import KV_KNOWLEDGE, kv_query, service_from_metadata


@Configuration()
class ImaQueryCommand(GeneratingCommand):
    question = Option(require=True, validate=validators.Match("question", r".+"))

    def generate(self):
        svc = service_from_metadata(self._metadata)
        rows = kv_query(svc, KV_KNOWLEDGE)
        needle = self.question.lower()
        for r in rows:
            hay = " ".join(
                str(r.get(k, "")) for k in ("topic", "summary", "tags")
            ).lower()
            if needle not in hay:
                continue
            yield {
                "_time": r.get("updated_at", ""),
                "topic": r.get("topic", ""),
                "summary": r.get("summary", ""),
                "evidence_count": r.get("evidence_count", 0),
                "confidence": r.get("confidence", 0),
                "tags": r.get("tags", ""),
            }


dispatch(ImaQueryCommand, sys.argv, sys.stdin, sys.stdout, __name__)
