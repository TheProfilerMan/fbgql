"""Synchronous transport backed by ``requests`` (default engine)."""

from __future__ import annotations

import time

import requests

from .. import config, policy
from ..errors import RateLimited, SessionInvalid, TransportError
from . import base


class SyncTransport:
    def __init__(self, timeout: float = 60.0):
        self.timeout = timeout
        self._session = requests.Session()

    def post_form(
        self,
        headers: dict[str, str],
        data: dict[str, str],
        cookies: dict[str, str],
        proxy: str | None = None,
    ) -> str:
        proxies = base.proxies_dict(proxy)
        last_exc: Exception | None = None
        for attempt in range(1, policy.MAX_TRANSPORT_RETRIES + 1):
            try:
                resp = self._session.post(
                    config.GRAPHQL_URL,
                    headers=headers,
                    data=data,
                    cookies=cookies,
                    proxies=proxies,
                    timeout=self.timeout,
                )
            except (requests.Timeout, requests.ConnectionError, requests.exceptions.ProxyError) as exc:
                last_exc = exc
                time.sleep(policy.transport_backoff_seconds(attempt))
                continue

            body = resp.text
            if resp.status_code == 200:
                return body
            if base.is_session_dead(resp.status_code, body):
                raise SessionInvalid("Facebook returned a login/checkpoint response")
            if base.is_blocked(resp.status_code, body):
                if attempt >= policy.MAX_TRANSPORT_RETRIES:
                    raise RateLimited(f"Blocked after {attempt} attempts (HTTP {resp.status_code})")
                time.sleep(policy.transport_backoff_seconds(attempt))
                continue
            # Other non-200: brief retry then fail.
            last_exc = TransportError(f"HTTP {resp.status_code}")
            time.sleep(policy.transport_backoff_seconds(attempt))

        raise TransportError(f"POST failed after retries: {last_exc}")

    def get(self, url: str, cookies: dict[str, str], proxy: str | None = None,
            headers: dict[str, str] | None = None) -> str:
        proxies = base.proxies_dict(proxy)
        resp = self._session.get(
            url,
            headers=headers or {"user-agent": config.BASE_HEADERS["user-agent"]},
            cookies=cookies,
            proxies=proxies,
            timeout=self.timeout,
        )
        return resp.text
