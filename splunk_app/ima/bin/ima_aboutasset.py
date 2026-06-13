#!/usr/bin/env python
"""Custom search command: | imaaboutasset asset="acct-prod-01"

Returns the per-asset institutional-memory card as a flat row stream so it
plays nicely with Splunk dashboards and saved-search pipelines.
"""
from __future__ import annotations

import os
import sys

_here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_here, "lib"))
sys.path.insert(0, _here)

from splunklib.searchcommands import (
    Configuration,
    GeneratingCommand,
    Option,
    dispatch,
    validators,
)

from _ima_common import build_asset_card


@Configuration()
class ImaAboutAssetCommand(GeneratingCommand):
    asset = Option(require=True, validate=validators.Match("asset", r".+"))

    def generate(self):
        card = build_asset_card(self.service, self.asset)
        if not card.get("found"):
            yield {
                "_time": "",
                "asset": card["asset"],
                "status": "no_memory",
                "annotation_count": 0,
            }
            return

        # Header row with aggregates
        yield {
            "_time": card.get("last_seen", ""),
            "asset": card["asset"],
            "status": "summary",
            "annotation_count": card["annotation_count"],
            "top_disposition": card["top_disposition"],
            "dispositions": ", ".join(f"{k}={v}" for k, v in card["dispositions"].items()),
            "analysts": ", ".join(f"{k}={v}" for k, v in card["analysts"].items()),
            "first_seen": card["first_seen"],
            "last_seen": card["last_seen"],
        }
        # One row per recent annotation
        for a in card["recent_annotations"]:
            yield {
                "_time": a["created_at"],
                "asset": card["asset"],
                "status": "annotation",
                "alert_id": a["alert_id"],
                "disposition": a["disposition"],
                "reason": a["reason"],
                "analyst": a["analyst"],
            }
        # One row per related knowledge entry
        for k in card["related_knowledge"]:
            yield {
                "_time": "",
                "asset": card["asset"],
                "status": "knowledge",
                "topic": k["topic"],
                "summary": k["summary"],
                "confidence": k["confidence"],
                "evidence_count": k["evidence_count"],
            }


dispatch(ImaAboutAssetCommand, sys.argv, sys.stdin, sys.stdout, __name__)
