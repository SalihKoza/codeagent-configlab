# eventlog — add time-window filtering to `EventStore.query`

`eventlog/store.py` provides `EventStore`, an in-memory store of `Event`s. Each event has an integer
`timestamp`, a `type` and a mapping of `fields`. Timestamps are plain `int`s: a larger value means a
later moment, they carry no unit or timezone of their own, and they are compared numerically.

`EventStore.query(type=None, *, where=None)` already filters by event type and by field values,
combines those filters with logical AND, and returns a new list ordered by ascending timestamp
(events with the same timestamp keep the order in which they were recorded).

## Feature request

Users need to restrict a query to a time window. Add two optional keyword arguments, `start` and
`end`, to `EventStore.query`. Their values are timestamps (`int`), like the events' timestamps.

```python
>>> from eventlog import EventStore
>>> store = EventStore()
>>> a = store.record(100, "login", user="ana")
>>> b = store.record(150, "click", user="ana")
>>> c = store.record(200, "logout", user="ana")
>>> store.query(start=100, end=200) == [a, b]
True
```

## Required behavior

1. `start` is **inclusive**: an event whose timestamp equals `start` is included.
2. `end` is **exclusive**: an event whose timestamp equals `end` is excluded.
3. If `start` is omitted or `None`, there is no lower bound. Only `None` means "no bound"; any
   `int`, including `0`, is a bound.
4. If `end` is omitted or `None`, there is no upper bound. Only `None` means "no bound"; any `int`,
   including `0`, is a bound.
5. If `start == end`, the result is empty.
6. If `start > end`, `query` raises `ValueError`. This happens regardless of the store's contents
   and of the other filters.
7. The time window combines with every existing filter (`type`, `where`) using logical AND: an
   event is returned only if it lies inside the window **and** matches all other given filters.
8. The existing result ordering is unchanged: ascending timestamp, with events of equal timestamp
   in the order they were recorded.
9. Calling `query` without either bound (both omitted, or both `None`) behaves exactly as it does
   today.
10. The return type (a new `list` of `Event`s) and the semantics of the existing `type` and `where`
    filters stay unchanged.

## Constraints

- Use only the Python standard library; do not add dependencies.
- Keep the existing parameters of `query` (`type`, and keyword-only `where`) with their current
  names, kinds and defaults, and do not change the behavior of any other part of the package beyond
  what the requirements above describe.

## Running the public tests

    python3 -m unittest tests.test_store -v
