#!/usr/bin/env python
"""Custom search command: | imaquery question="what do we know about X?"

Splunk's SPL parser rejects underscores in command names, so the stanza in
commands.conf is `imaquery` even though this file is named `ima_query.py`.

Usage in Splunk search bar:
  | imaquery question="finance Monday"
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

from _ima_common import KV_KNOWLEDGE, kv_query


@Configuration()
class ImaQueryCommand(GeneratingCommand):
    question = Option(require=True, validate=validators.Match("question", r".+"))

    def generate(self):
        rows = kv_query(self.service, KV_KNOWLEDGE)
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
