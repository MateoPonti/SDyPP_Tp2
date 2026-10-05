import asyncio

from shared.clock import LamportClock


def test_lamport_tick_and_receive_preserve_causal_order() -> None:
    async def scenario() -> None:
        clock = LamportClock()
        assert await clock.tick() == 1
        assert await clock.receive(8) == 9
        assert await clock.tick() == 10

    asyncio.run(scenario())
