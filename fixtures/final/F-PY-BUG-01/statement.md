# msgheaders — `Headers.set` leaves old case variants behind

`msgheaders/headers.py` provides `Headers`, an ordered collection of message headers. It stores
`(name, value)` entries in insertion order and may hold several entries for the same header.
Header names are ASCII strings and are documented as **case-insensitive**: two names refer to the
same header when they are equal ignoring case (`"Content-Type"`, `"content-type"` and
`"CONTENT-TYPE"` match each other; `"Accept"` and `"Accept-Encoding"` do not).

`Headers` has separate operations for appending (`add`), replacing (`set`), reading (`get`,
`get_all`, `in`) and inspecting the stored entries (iteration, `items()`, `len()`).

## Bug report

`set` does not treat header names case-insensitively when it looks for existing entries to
replace. Entries whose name differs from the `set` argument only in case survive, so the collection
ends up with several entries for a header that was just replaced, and lookups return stale values:

```python
>>> from msgheaders import Headers
>>> h = Headers([("Content-Type", "text/plain"), ("CONTENT-TYPE", "text/html")])
>>> h.set("content-type", "application/json")
>>> h.items()
[('Content-Type', 'text/plain'), ('CONTENT-TYPE', 'text/html'), ('content-type', 'application/json')]
>>> h.get("Content-Type")
'text/plain'
```

Expected: `h.items() == [("content-type", "application/json")]` and
`h.get("Content-Type") == "application/json"`.

## Required behavior of `set(name, value)`

Fix `set` so that it follows this contract for every input:

1. Header names are compared case-insensitively (equal ignoring case).
2. `set` removes **all** existing entries whose name matches `name`, regardless of their spelling
   and of how many there are.
3. Afterwards exactly one entry for that header remains: the new `(name, value)` entry.
4. The new entry's stored name is spelled exactly as the `name` argument passed to `set`.
5. The new entry is appended at the **end** of the collection, after the matching entries have
   been removed.
6. All entries whose names do not match keep their stored spelling, their values and their
   relative order.
7. If no entry matches, `set` simply appends the new entry.

## Unchanged behavior

8. `add` is unchanged: it always appends a new entry and may still create several entries for the
   same header, including entries whose names differ only in case.
9. Public method signatures and return types stay unchanged (`set` and `add` return `None`;
   `get_all` and `items` return lists).
10. `get`, `get_all`, `in`, `len()`, iteration and `items()` keep their current semantics; after a
    `set` they simply observe the corrected entries.

## Constraints

- Use only the Python standard library; do not add dependencies.
- Do not change the behavior of any other part of `Headers` beyond what the contract above
  requires.

## Running the public tests

    python3 -m unittest tests.test_headers -v
