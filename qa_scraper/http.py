"""Shared async HTTP client: overall + per-host concurrency limits, retries with
backoff on rate limits / server errors, and never raises on network failure
(returns None instead, so one dead board can't kill a run)."""
from __future__ import annotations

import asyncio
import random
from collections import defaultdict
from urllib.parse import urlparse

import httpx

from . import config


LONG_BLOCK = 300        # seconds; a longer Retry-After means "come back later", not "slow down"


class Http:
    def __init__(self):
        self.client = httpx.AsyncClient(
            timeout=config.REQUEST_TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": config.USER_AGENT, "Accept": "application/json, text/html;q=0.9, */*;q=0.8"},
            limits=httpx.Limits(max_connections=config.MAX_CONCURRENCY * 2),
        )
        self._global = asyncio.Semaphore(config.MAX_CONCURRENCY)
        self._hosts: dict[str, asyncio.Semaphore] = {}
        self.errors: list[str] = []
        # Hosts that asked us to stay away for a long time (429 with a long Retry-After, e.g.
        # Workable's daily limit). We stop calling them for the rest of the run.
        self.blocked: dict[str, float] = {}

    def _host_sem(self, host: str) -> asyncio.Semaphore:
        sem = self._hosts.get(host)
        if sem is None:
            sem = self._hosts[host] = asyncio.Semaphore(config.HOST_LIMITS.get(host, config.PER_HOST_CONCURRENCY))
        return sem

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        await self.client.aclose()

    async def request(self, method: str, url: str, **kw) -> httpx.Response | None:
        host = urlparse(url).netloc
        if host in self.blocked:
            return None
        for attempt in range(config.RETRIES):
            try:
                async with self._global, self._host_sem(host):
                    r = await self.client.request(method, url, **kw)
                if r.status_code == 429 or r.status_code >= 500:
                    try:
                        after = float(r.headers.get("Retry-After", 0) or 0)
                    except ValueError:
                        after = 0
                    if r.status_code == 429 and after > LONG_BLOCK:
                        self.blocked[host] = after
                        self.errors.append(f"{host}: rate limit, asked to wait {int(after)}s; skipped for this run")
                        return None
                    wait = after or (2 ** attempt + random.random())
                    await asyncio.sleep(min(wait, 30))
                    continue
                return r
            except (httpx.HTTPError, OSError) as e:
                if attempt == config.RETRIES - 1:
                    self.errors.append(f"{method} {url}: {type(e).__name__}")
                    return None
                await asyncio.sleep(2 ** attempt + random.random())
        return None

    async def get_json(self, url: str, **kw):
        r = await self.request("GET", url, **kw)
        if r is None or r.status_code >= 400:
            return None
        try:
            return r.json()
        except ValueError:
            return None

    async def post_json(self, url: str, payload: dict, **kw):
        r = await self.request("POST", url, json=payload, **kw)
        if r is None or r.status_code >= 400:
            return None
        try:
            return r.json()
        except ValueError:
            return None

    async def get_text(self, url: str, **kw) -> str | None:
        r = await self.request("GET", url, **kw)
        if r is None or r.status_code >= 400:
            return None
        return r.text
