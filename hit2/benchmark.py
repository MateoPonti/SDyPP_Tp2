"""Throughput experiment for HIT 2.

Examples:
    python hit2/benchmark.py --workers 1 --tasks 100
    python hit2/benchmark.py --workers 8 --tasks 100
"""

import argparse
import asyncio
import time

import httpx


async def run(server: str, workers: int, tasks: int) -> None:
    payload = {"calculation": "add", "parameters": [1, 2], "lamport_timestamp": 0}
    started = time.perf_counter()
    async with httpx.AsyncClient(base_url=server, timeout=300) as client:
        responses = await asyncio.gather(
            *(client.post("/getRemoteTask", json=payload) for _ in range(tasks))
        )
    elapsed = time.perf_counter() - started
    successful = sum(response.is_success for response in responses)
    throughput = successful / elapsed * 60 if elapsed else 0
    print(
        f"workers={workers} tasks={successful} elapsed_s={elapsed:.3f} "
        f"throughput_per_min={throughput:.2f}"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", default="http://localhost:8000")
    parser.add_argument("--workers", type=int, required=True)
    parser.add_argument("--tasks", type=int, default=100)
    args = parser.parse_args()
    asyncio.run(run(args.server, args.workers, args.tasks))
