from bisect import bisect_left
from collections import deque
from threading import Lock
from time import perf_counter


class RateMeter:
    """
    This class allows to measure the rate of an iterative code.
    The rate value is calculated taking into account only the last `interval`
    seconds, so the measure can calculate the measured rate in real time.

    Instances are safe to share between threads: every method that reads or
    writes the stored samples holds an internal lock.
    """

    def __init__(self, interval=1.0):
        """
        Returns a :class:`RateMeter` instance.

        :param interval: Interval value for rate measurement, in seconds.
                         Rate will be calculated over the last `interval`
                         seconds.
        """
        self._times = deque()
        self._iters = deque()
        self._lock = Lock()
        self.interval = interval

    def restart(self):
        """
        Restarts this :class:`RateMeter` instance, removing all stored data.
        """
        with self._lock:
            self._times.clear()
            self._iters.clear()

    def _remove_past_items(self):
        """
        Internal function. Removes all data stored before `interval` seconds.

        The caller must hold `self._lock`.
        """
        first_time_value = self._times[-1] - self.interval
        first_time_index = bisect_left(self._times, first_time_value)

        # Time difference between last and first items must remain
        # equal or greater than 'interval'
        if self._times.count(first_time_value) == 0:
            first_time_index -= 1

        for _ in range(first_time_index):
            self._times.popleft()
            self._iters.popleft()

    def update(self, iter_num=None):
        """
        Add a time reference for a new code iteration.

        :param iter_num: Current iteration number. If not set, the
                         previous iteration count value increased by 1
                         will be taken.
        """
        with self._lock:
            if iter_num is None:
                iter_num = self._iters[-1] + 1 if len(self._iters) > 0 else 0
            # Read the clock inside the lock. Timestamping outside it lets two
            # threads append in the opposite order to the one they sampled in,
            # which leaves `_times` unsorted and silently breaks the bisect in
            # `_remove_past_items()` and `rate_at()`.
            t_current = perf_counter()
            self._times.append(t_current)
            self._iters.append(iter_num)
            self._remove_past_items()

    def rate(self):
        """
        Calculates the rate over the last `interval` seconds.

        :return: Measured rate, or 0 if there is no data.
        """
        with self._lock:
            if len(self._times) <= 1:
                return 0

            value_diff = self._iters[-1] - self._iters[0]
            time_diff = self._times[-1] - self._times[0]
            return 0 if time_diff == 0 else value_diff / time_diff

    def rate_at(self, now=None):
        """
        Rate over the last `interval` seconds, measured as of `now`.

        Unlike :meth:`rate`, whose window ends at the most recent sample, this
        one ends at `now`. The value therefore decays as time passes with no
        new samples, and reaches 0 once the last sample has left the window.

        Like :meth:`rate`, this counts the intervals *between* samples, so a
        window holding a single sample reports 0.

        This method never mutates the stored samples, so asking for the rate
        does not prune the window that the next answer depends on.

        :param now: Reference instant, on the same clock as `perf_counter()`.
                    Defaults to the current time.
        :return: Measured rate, or 0 if fewer than two samples fall in the
                 window.
        """
        with self._lock:
            at = perf_counter() if now is None else now

            if not self._times:
                return 0

            first = bisect_left(self._times, at - self.interval)
            if first >= len(self._times):
                return 0

            value_diff = self._iters[-1] - self._iters[first]
            time_diff = at - self._times[first]

            return 0 if time_diff <= 0 else value_diff / time_diff
