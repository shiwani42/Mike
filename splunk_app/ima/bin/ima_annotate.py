#!/usr/bin/env python
"""Custom search command: | imaannotate ...

Records an analyst annotation into the ima_annotations KV Store collection.
Stanza is `imaannotate` (no underscore, per Splunk's SPL parser rules).

Usage in Splunk search bar:
  | imaannotate alert_id="NOTABLE-1234" disposition="false_positive" reason="Finance Monday batch" asset="acct-prod-01"
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
)

from _ima_common import KV_ANNOTATIONS, kv_insert, now_iso


@Configuration()
class ImaAnnotateCommand(GeneratingCommand):
    alert_id = Option(require=True)
    disposition = Option(require=True)
    reason = Option(require=True)
    analyst = Option(require=False, default="")
    asset = Option(require=False, default="")
    event_type = Option(require=False, default="")
    source_ip = Option(require=False, default="")

    def generate(self):
        record = {
            "alert_id": self.alert_id,
            "event_type": self.event_type,
            "analyst": self.analyst or self._metadata.searchinfo.username,
            "disposition": self.disposition,
            "reason": self.reason,
            "source_ip": self.source_ip,
            "asset": self.asset,
            "created_at": now_iso(),
        }
        key = kv_insert(self.service, KV_ANNOTATIONS, record)
        yield {
            "_time": record["created_at"],
            "status": "saved",
            "_key": key,
            "alert_id": self.alert_id,
            "disposition": self.disposition,
        }


dispatch(ImaAnnotateCommand, sys.argv, sys.stdin, sys.stdout, __name__)
