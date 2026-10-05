import asyncio


class LamportClock:
    def __init__(self, initial: int = 0) -> None:
        self._value = initial
        self._lock = asyncio.Lock()

    @property
    def value(self) -> int:
        return self._value

    async def tick(self) -> int:
        async with self._lock:
            self._value += 1
            return self._value

    async def receive(self, remote_timestamp: int) -> int:
        async with self._lock:
            self._value = max(self._value, remote_timestamp) + 1
            return self._value
