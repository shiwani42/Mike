#!/usr/bin/env python
"""Custom search command: | ima_build

Clusters annotations by (event_type, disposition), calls the local LLM
(Ollama by default) on each cluster, and writes structured knowledge entries
into the ima_knowledge collection.
Usage in Splunk search bar:
  | ima_build
"""
from __future__ import annotations

import sys
from collections import defaultdict

from splunklib.searchcommands import Configuration, GeneratingCommand, dispatch

from _ima_common import (
    KV_ANNOTATIONS,
    KV_KNOWLEDGE,
    kv_insert,
    kv_query,
    llm_extract,
    now_iso,
    service_from_metadata,
)


@Configuration()
class ImaBuildCommand(GeneratingCommand):
    def generate(self):
        svc = service_from_metadata(self._metadata)
        annotations = kv_query(svc, KV_ANNOTATIONS)
        if not annotations:
            yield {"_time": now_iso(), "status": "no_annotations", "message": "Run ima_annotate first."}
            return

        buckets: dict[tuple[str, str], list[dict]] = defaultdict(list)
        for a in annotations:
            buckets[(a.get("event_type", ""), a.get("disposition", ""))].append(a)

        for (event_type, disposition), items in buckets.items():
            notes = " | ".join(i.get("reason", "") for i in items if i.get("reason"))
            structured = llm_extract(notes)
            record = {
                "topic": f"{event_type or 'unknown'} :: {disposition or 'unknown'}",
                "summary": structured.get("behavior_pattern") or notes[:280],
                "evidence_count": len(items),
                "confidence": float(structured.get("confidence", 0.0)),
                "tags": ",".join(structured.get("tags") or []),
                "updated_at": now_iso(),
            }
            key = kv_insert(svc, KV_KNOWLEDGE, record)
            yield {
                "_time": record["updated_at"],
                "status": "wrote_entry",
                "_key": key,
                "topic": record["topic"],
                "summary": record["summary"],
                "evidence_count": record["evidence_count"],
                "confidence": record["confidence"],
                "tags": record["tags"],
            }


dispatch(ImaBuildCommand, sys.argv, sys.stdin, sys.stdout, __name__)
