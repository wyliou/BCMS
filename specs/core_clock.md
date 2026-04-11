# Spec: core/clock

Module: `backend/src/app/core/clock.py` | Tests: `backend/tests/unit/core/test_clock.py` | FRs: (none — shared utility §5.1)

## Exports

```python
def now_utc() -> datetime:
    """Return the current UTC time as a timezone-aware datetime.

    Returns:
        datetime: Current UTC datetime with tzinfo=timezone.utc.
    """
```

## Imports

- `datetime`: `datetime`, `timezone`

## Side Effects

None. Pure function wrapping `datetime.now(tz=timezone.utc)`.

## Tests

1. `test_now_utc_is_timezone_aware` — result has `tzinfo` set (not naive).
2. `test_now_utc_is_utc` — `result.tzinfo == timezone.utc`.
3. `test_now_utc_is_patchable` — monkeypatching `app.core.clock.now_utc` returns a fixed value; consumers see the patched value.
4. `test_now_utc_advances` — two successive calls return non-decreasing timestamps.
5. `test_no_direct_datetime_now_in_src` — grep `backend/src/app/` for `datetime.now()` without `tz=`; assert zero matches (pipeline-level guard, not a unit test per se, but worth noting here).

## Constraints

None.

## Gotchas

- Never use `datetime.utcnow()` (naive) or `datetime.now()` (local TZ) anywhere in `src/`. This single function is the mandatory seam.
- The fixture pattern is `monkeypatch.setattr("app.core.clock.now_utc", lambda: fixed_dt)`.
