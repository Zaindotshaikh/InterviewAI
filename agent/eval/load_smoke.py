"""Tiny load/smoke script: hammers /api/v2/interview/health and languages."""

from __future__ import annotations

import argparse
import asyncio
import time

import httpx


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:3001")
    parser.add_argument("--n", type=int, default=50)
    args = parser.parse_args()

    async with httpx.AsyncClient(base_url=args.base, timeout=10.0) as client:
        start = time.perf_counter()
        ok = 0
        for _ in range(args.n):
            r = await client.get("/api/v2/interview/health")
            if r.status_code == 200:
                ok += 1
        elapsed = time.perf_counter() - start
        print(f"health ok={ok}/{args.n} in {elapsed:.2f}s ({args.n / elapsed:.1f} rps)")


if __name__ == "__main__":
    asyncio.run(main())
