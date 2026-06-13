#!/usr/bin/env python
"""Minimal smoke-test custom search command.

  | imaping

Just yields one record. If this works but | imaquery doesn't, the problem is
in our code (not in the splunklib environment / commands.conf wiring).
"""
from __future__ import annotations

import os
import sys
import traceback


def _dump(msg: str) -> None:
    try:
        with open(os.path.expandvars(r"%USERPROFILE%\ima_debug.log"), "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except Exception:
        pass


try:
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
    from splunklib.searchcommands import Configuration, GeneratingCommand, dispatch

    @Configuration()
    class ImaPingCommand(GeneratingCommand):
        def generate(self):
            yield {"_time": 0, "msg": "pong", "python": sys.version.split()[0]}

    dispatch(ImaPingCommand, sys.argv, sys.stdin, sys.stdout, __name__)
except Exception:
    _dump("=== imaping CRASHED ===\n" + traceback.format_exc())
    raise
