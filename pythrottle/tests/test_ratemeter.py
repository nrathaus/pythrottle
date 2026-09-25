import os
import threading
import time

import pytest

from pythrottle.rate_meter import RateMeter
from pythrottle.throttle import Throttle


RATE = 1000
INTERVAL = 2.0
# Same knob and default as test_throttle.py, which tox sets via
# THROTTLE_TEST_MAX_ERROR. RateMeter holds a lock across update()/rate(), so
# callers now wait where they previously raced; that costs a little timing
# precision, and a hard-coded 0.01% bound flaked under it.
MAX_ERROR = float(os.getenv("THROTTLE_TEST_MAX_ERROR", "0.03")) / 100


@pytest.fixture(name="throttle")
def throttle_fxt():
    """
    Yields a :class:`Throttle` instance with the default rate.
    """
    yield Throttle(interval=(1 / RATE))


@pytest.fixture(name="rate_meter")
def rate_meter_fxt():
    return RateMeter(interval=INTERVAL)


def assert_results(rate_meter, values):
    mean = sum(values) / len(values)
    assert abs(1 - mean / RATE) < MAX_ERROR
    assert abs(1 - rate_meter.rate() / RATE) < MAX_ERROR

    rate_meter.restart()
    assert rate_meter.rate() == 0
    assert len(rate_meter._iters) == 0
    assert len(rate_meter._times) == 0


def test_ratemeter_non_consecutive_update(throttle, rate_meter):
    """
    Tests the measurement of the rate of an iterative code using
    `update()` in non-consecutive iterations.
    """
    iters = 5 * RATE
    values = []

    assert rate_meter.rate() == 0

    for i in throttle.loop(iters):
        if i % 5 == 0:
            rate_meter.update(i)
        measured_rate = rate_meter.rate()
        if i > measured_rate != 0:
            values.append(measured_rate)

    assert_results(rate_meter, values)


def test_ratemeter_default_update_param(throttle, rate_meter):
    """
    Tests the measurement of the rate of an iterative code using
    `update()` with default parameter in each iteration.
    """
    iters = 5 * RATE
    values = []

    assert rate_meter.rate() == 0

    for i in throttle.loop(iters):
        rate_meter.update()
        measured_rate = rate_meter.rate()
        if i > measured_rate != 0:
            values.append(measured_rate)

    assert_results(rate_meter, values)


# --- rate_at() -------------------------------------------------------------

# Synthetic samples are built on exact binary fractions from 0.0 so that the
# expected rates below are exact and the tests carry no timing tolerance.
SPACING = 1 / 64
SAMPLES = 32
RATE_AT_INTERVAL = 1.0


def synthetic_meter(samples=SAMPLES, spacing=SPACING,
                    interval=RATE_AT_INTERVAL):
    """
    Returns a :class:`RateMeter` holding `samples` samples spaced `spacing`
    seconds apart, the first at 0.0, bypassing `update()` so the sample times
    are exact.
    """
    meter = RateMeter(interval=interval)
    for i in range(samples):
        meter._times.append(i * spacing)
        meter._iters.append(i)
    return meter


def test_rate_at_empty_meter():
    """
    `rate_at()` on a meter with no samples returns 0 rather than raising,
    matching the guard `rate()` already has.
    """
    meter = RateMeter(interval=RATE_AT_INTERVAL)
    assert meter.rate_at() == 0
    assert meter.rate_at(123.0) == 0


def test_rate_at_single_sample():
    """
    A window holding one sample has no interval to measure, so it reports 0,
    consistently with `rate()`.
    """
    meter = synthetic_meter(samples=1)
    assert meter.rate() == 0
    assert meter.rate_at(0.0) == 0


def test_rate_at_last_sample_matches_rate():
    """
    Measured as of the most recent sample, `rate_at()` spans exactly the same
    window as `rate()` and must agree with it.
    """
    meter = synthetic_meter()
    last = (SAMPLES - 1) * SPACING
    assert meter.rate() == 64.0
    assert meter.rate_at(last) == meter.rate()


def test_rate_at_decays_without_update():
    """
    The window ends at `now`, so with no new samples the rate falls
    monotonically as `now` advances.
    """
    meter = synthetic_meter()
    last = (SAMPLES - 1) * SPACING
    seen = [meter.rate_at(last + step) for step in (0.0, 0.25, 0.5, 0.75)]
    assert all(b < a for a, b in zip(seen, seen[1:])), seen


def test_rate_at_expected_values():
    """
    Checks `rate_at()` against hand-computed values at three points: the last
    sample, one interval later, and a quarter interval past that.
    """
    meter = synthetic_meter()
    assert meter.rate_at((SAMPLES - 1) * SPACING) == 64.0
    assert meter.rate_at(1.0) == 31.0
    assert meter.rate_at(1.25) == 15.0


def test_rate_at_zero_once_window_empties():
    """
    Once the last sample is more than `interval` behind `now`, no sample falls
    in the window and the rate is 0.
    """
    meter = synthetic_meter()
    last = (SAMPLES - 1) * SPACING
    assert meter.rate_at(last + RATE_AT_INTERVAL + 0.01) == 0


def test_rate_at_does_not_mutate():
    """
    Reading the rate must not prune the window the next read depends on.
    """
    meter = synthetic_meter()
    times, iters = list(meter._times), list(meter._iters)

    for at in (0.0, 0.5, 1.0, 10.0):
        meter.rate_at(at)

    assert list(meter._times) == times
    assert list(meter._iters) == iters


def test_rate_at_defaults_to_now():
    """
    Called with no argument, `rate_at()` measures as of the current time, so
    it decays while `rate()` stays frozen at the last recorded sample.
    """
    meter = RateMeter(interval=RATE_AT_INTERVAL)
    for _ in range(10):
        meter.update()

    frozen = meter.rate()
    first = meter.rate_at()
    time.sleep(0.1)
    second = meter.rate_at()

    assert meter.rate() == frozen
    assert second < first


def test_rate_at_reaches_zero_after_real_pause():
    """
    The documented promise that the rate covers only the last `interval`
    seconds: one interval after the final `update()`, the rate is 0.
    """
    meter = RateMeter(interval=0.2)
    for _ in range(10):
        meter.update()

    assert meter.rate_at() > 0
    time.sleep(0.25)
    assert meter.rate_at() == 0


def test_concurrent_update_keeps_times_sorted():
    """
    Regression guard: `update()` must timestamp inside the lock. Reading the
    clock outside it lets two threads append in the opposite order to the one
    they sampled in, leaving `_times` unsorted, which silently breaks the
    bisect in `_remove_past_items()` and `rate_at()`.
    """
    meter = RateMeter(interval=RATE_AT_INTERVAL)
    stop = time.perf_counter() + 0.5
    errors = []

    def worker():
        try:
            while time.perf_counter() < stop:
                meter.update()
                meter.rate_at()
        except Exception as exc:          # pragma: no cover - reported below
            errors.append(f"{type(exc).__name__}: {exc}")

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, errors
    assert len(meter._times) == len(meter._iters)

    times = list(meter._times)
    inversions = [i for i, (a, b) in enumerate(zip(times, times[1:]))
                  if b < a]
    assert not inversions, f"{len(inversions)} out-of-order timestamps"
