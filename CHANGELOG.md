# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project uses a date-based version scheme, `(YYYY-2020).MM.DD`, so a
release cut on 2026-09-25 is version `6.9.25`.

## [6.9.25] - 2026-09-25
### Added
- `RateMeter.rate_at()`, which measures the rate over the last `interval`
  seconds as of a given instant rather than as of the most recent sample, so
  the value decays while no samples are recorded and reaches 0 once the window
  empties. `rate()` is unchanged.
- `RateMeter` is now thread-safe: an internal lock is held across `update()`,
  `restart()`, `rate()` and `rate_at()`.

### Fixed
- `update()` read the clock before taking the lock, so concurrent callers could
  append timestamps out of order and leave `_times` unsorted, silently breaking
  the bisect in `_remove_past_items()` and giving wrong rates.
- `rate_at()` counted samples recorded after `now` while dividing by the time
  elapsed only up to it, so a `now` behind the most recent sample returned an
  inflated rate: a 10/s stream read 200/s measured a twentieth of the way in.
  The numerator is now bounded by `now`. The forward case, which every pacing
  caller uses, is unchanged.
- `_remove_past_items()` scanned the whole window with `deque.count()` on every
  `update()`, an O(n) cost now serialised by the lock. Replaced with a single
  index compare. Four threads calling `update()` for one second went from
  roughly 11,000 samples to over 100,000 on the development host.

### Documentation
- `rate_at()` documented only that its window *ends* at `now`. Both ends differ
  from `rate()`: pruning deliberately retains one sample older than
  `last - interval`, which `rate_at()` excludes, so the two disagree even when
  `now` is the most recent sample. The divergence is intended and is now stated
  and pinned by a test.

### Changed
- Version scheme moved from Semantic Versioning to `(YYYY-2020).MM.DD`.

## [0.1.1](https://github.com/flusflas/pythrottle/releases/tag/v0.1.1) - 2020-04-04
### Added
- PyPI, Python versions and documentation badges.
- Update Sphinx documentation.

## [0.1.0](https://github.com/flusflas/pythrottle/releases/tag/v0.1.0) - 2020-04-04
### Added
- First version. Changelog started.
- `throttle` and `rate_meter` modules.
- Sphinx documentation
- Continuous integration testing with Travis CI.
