import asyncio

from app.providers.mailboxlayer.politeness import Politeness


async def test_concurrency_never_exceeds_max():
    pol = Politeness(max_concurrent=2, min_interval_seconds=0)
    in_flight = 0
    peak = 0

    async def worker():
        nonlocal in_flight, peak
        async with pol:
            in_flight += 1
            peak = max(peak, in_flight)
            await asyncio.sleep(0.01)
            in_flight -= 1

    await asyncio.gather(*(worker() for _ in range(8)))
    assert peak <= 2


async def test_spacing_respects_min_interval():
    waits: list[float] = []

    class FakeClock:
        def __init__(self) -> None:
            self.t = 0.0

        def __call__(self) -> float:
            return self.t

        async def sleep(self, d: float) -> None:
            waits.append(d)
            self.t += d

    fc = FakeClock()
    pol = Politeness(max_concurrent=4, min_interval_seconds=0.5, clock=fc, sleep=fc.sleep)
    # No real time passes between acquisitions, so each after the first must wait.
    for _ in range(3):
        async with pol:
            pass
    assert len(waits) == 2
    assert all(w >= 0.5 for w in waits)
