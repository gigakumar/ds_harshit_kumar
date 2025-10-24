import asyncio
from typing import Callable, Awaitable, Dict


class Scheduler:
    """Very small asyncio interval scheduler."""

    def __init__(self):
        self._tasks: Dict[str, asyncio.Task] = {}

    def add_interval_job(self, name: str, fn: Callable[[], Awaitable[None]], seconds: int) -> None:
        if name in self._tasks:
            raise ValueError(f"Job already exists: {name}")

        async def runner():
            try:
                while True:
                    await fn()
                    await asyncio.sleep(max(1, int(seconds)))
            except asyncio.CancelledError:
                return

        self._tasks[name] = asyncio.create_task(runner(), name=f"job:{name}")

    def cancel(self, name: str) -> None:
        t = self._tasks.pop(name, None)
        if t:
            t.cancel()

    def cancel_all(self) -> None:
        for name in list(self._tasks.keys()):
            self.cancel(name)
