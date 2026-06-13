from __future__ import annotations

import ssl
from functools import lru_cache

import splunklib.client as splunk_client

from .config import Settings, load


def _ssl_context(verify: bool) -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    if not verify:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    return ctx


@lru_cache(maxsize=1)
def service() -> splunk_client.Service:
    s: Settings = load()
    kwargs = dict(
        host=s.host,
        port=s.port,
        scheme=s.scheme,
        app=s.app,
        owner=s.owner,
        context=_ssl_context(s.verify_tls),
    )
    if s.token:
        svc = splunk_client.connect(token=s.token, **kwargs)
    elif s.username and s.password:
        svc = splunk_client.connect(username=s.username, password=s.password, **kwargs)
    else:
        raise RuntimeError(
            "No Splunk credentials configured. Set SPLUNK_TOKEN or "
            "SPLUNK_USERNAME + SPLUNK_PASSWORD in .env."
        )
    return svc


def reset() -> None:
    service.cache_clear()
