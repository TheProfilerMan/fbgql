"""Asynchronous transport backed by ``httpx`` (engine="async").

Mirrors SyncTransport's behavior exactly, using the same classification helpers and
backoff schedule so the two engines are behaviorally identical.
"""

from __future__ import annotations

import asyncio

import httpx

from .. import config, policy
from ..errors import RateLimited, SessionInvalid, TransportError
from . import base


class AsyncTransport:
    def __init__(self, timeout: float = 60.0):
        self.timeout = timeout

    async def post_form(
        self,
        headers: dict[str, str],
        data: dict[str, str],
        cookies: dict[str, str],
        proxy: str | None = None,
    ) -> str:
        last_exc: Exception | None = None
        async with httpx.AsyncClient(timeout=self.timeout, proxy=proxy, follow_redirects=True) as client:
            for attempt in range(1, policy.MAX_TRANSPORT_RETRIES + 1):
                try:
                    resp = await client.post(
                        config.GRAPHQL_URL, headers=headers, data=data, cookies=cookies
                    )
                except (httpx.TimeoutException, httpx.TransportError) as exc:
                    last_exc = exc
                    await asyncio.sleep(policy.transport_backoff_seconds(attempt))
                    continue

                body = resp.text
                if resp.status_code == 200:
                    return body
                if base.is_session_dead(resp.status_code, body):
                    raise SessionInvalid("Facebook returned a login/checkpoint response")
                if base.is_blocked(resp.status_code, body):
                    if attempt >= policy.MAX_TRANSPORT_RETRIES:
                        raise RateLimited(
                            f"Blocked after {attempt} attempts (HTTP {resp.status_code})"
                        )
                    await asyncio.sleep(policy.transport_backoff_seconds(attempt))
                    continue
                last_exc = TransportError(f"HTTP {resp.status_code}")
                await asyncio.sleep(policy.transport_backoff_seconds(attempt))

        raise TransportError(f"POST failed after retries: {last_exc}")

    async def get(self, url: str, cookies: dict[str, str], proxy: str | None = None,
                  headers: dict[str, str] | None = None) -> str:
        async with httpx.AsyncClient(timeout=self.timeout, proxy=proxy, follow_redirects=True) as client:
            resp = await client.get(
                url,
                headers=headers or {"user-agent": config.BASE_HEADERS["user-agent"]},
                cookies=cookies,
            )
            return resp.text
