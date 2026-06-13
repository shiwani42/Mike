#!/usr/bin/env python
"""Modular Input: ima_autobuild

Runs continuously inside Splunk on the configured interval (default 300 sec).
Clusters annotations by (event_type, disposition), calls the local LLM
(Ollama / Foundation-Sec), and rebuilds ima_knowledge so the institutional
graph stays in sync with whatever analysts (or external MCP clients) wrote
into ima_annotations since the last tick.

This is the autonomous agentic-ops loop: no human needs to run `ima knowledge
build` or `| imabuild` — the agent runs continuously inside Splunk.

Enable via Splunk Web -> Settings -> Data inputs -> "IMA Autobuild".
"""
from __future__ import annotations

import os
import sys
from collections import defaultdict

_here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_here, "lib"))
sys.path.insert(0, _here)

from splunklib.modularinput import Argument, Event, EventWriter, Scheme, Script

from _ima_common import (
    KV_ANNOTATIONS,
    KV_KNOWLEDGE,
    kv_insert,
    kv_query,
    llm_extract,
    now_iso,
)


class ImaAutobuildInput(Script):
    def get_scheme(self) -> Scheme:
        scheme = Scheme("IMA Autobuild")
        scheme.description = (
            "Continuously rebuilds the IMA institutional-knowledge graph from "
            "the ima_annotations KV Store collection. Runs the LLM extraction "
            "loop on every tick."
        )
        scheme.use_external_validation = False
        scheme.use_single_instance = False

        notes = Argument("notes")
        notes.description = "Free-form notes about this input. Optional."
        notes.required_on_create = False
        scheme.add_argument(notes)
        return scheme

    def stream_events(self, inputs, ew: EventWriter) -> None:
        for input_name in inputs.inputs:
            try:
                self._tick(input_name, ew)
            except Exception as exc:  # noqa: BLE001
                ew.log(
                    EventWriter.ERROR,
                    f"ima_autobuild tick failed for {input_name}: {exc}",
                )

    def _tick(self, input_name: str, ew: EventWriter) -> None:
        svc = self.service
        annotations = kv_query(svc, KV_ANNOTATIONS)
        if not annotations:
            ew.write_event(Event(
                data='status="idle" reason="no annotations yet"',
                source=input_name,
                sourcetype="ima:autobuild",
            ))
            return

        buckets: dict[tuple[str, str], list[dict]] = defaultdict(list)
        for a in annotations:
            buckets[(a.get("event_type", ""), a.get("disposition", ""))].append(a)

        # Full rebuild: clear existing knowledge so reruns don't duplicate.
        coll = svc.kvstore[KV_KNOWLEDGE]
        for e in kv_query(svc, KV_KNOWLEDGE):
            try:
                coll.data.delete_by_id(e["_key"])
            except Exception:  # noqa: BLE001
                pass

        written = 0
        for (event_type, disposition), items in buckets.items():
            notes_text = " | ".join(i.get("reason", "") for i in items if i.get("reason"))
            structured = llm_extract(notes_text)
            record = {
                "topic": f"{event_type or 'unknown'} :: {disposition or 'unknown'}",
                "summary": structured.get("behavior_pattern") or notes_text[:280],
                "evidence_count": len(items),
                "confidence": float(structured.get("confidence", 0.0)),
                "tags": ",".join(structured.get("tags") or []),
                "updated_at": now_iso(),
            }
            kv_insert(svc, KV_KNOWLEDGE, record)
            written += 1

        ew.write_event(Event(
            data=(
                f'status="built" annotations={len(annotations)} '
                f'clusters={len(buckets)} knowledge_entries_written={written}'
            ),
            source=input_name,
            sourcetype="ima:autobuild",
        ))


if __name__ == "__main__":
    sys.exit(ImaAutobuildInput().run(sys.argv))
