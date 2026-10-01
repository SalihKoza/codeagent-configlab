# rangefmt — collapse_ranges bug fix

`rangefmt/core.py` provides `collapse_ranges(values)`, which renders a sorted list of distinct
integers as a compact, comma-separated range string.

## Contract

- `values` is a list of integers in strictly ascending order, with no duplicates. It may be empty.
  It may contain negative integers.
- The return value is a string. Split the input into maximal runs of consecutive integers (each
  run's neighbours differ by exactly 1).
- A run containing exactly one integer `n` is rendered as `str(n)`.
- A run containing two or more integers, from `start` to `end`, is rendered as `f"{start}..{end}"`
  (two literal dots — this applies even when the run has exactly two integers, e.g. `[6, 7]`
  renders as `"6..7"`, not `"6,7"`). The `..` separator is used (instead of `-`) because it stays
  unambiguous when `start` or `end` is negative, e.g. `[-8, -7, -6]` renders as `"-8..-6"`.
- The rendered runs are joined with `,` (a single comma, no spaces), in the same order as the
  input.
- An empty input returns `""`.
- `collapse_ranges` does not modify the input list.

## Example

```python
>>> collapse_ranges([1, 2, 3, 5, 8])
'1..3,5,8'
```

## Bug report

For some inputs whose **last** run has two or more integers, the final run is rendered
incorrectly (dropping or truncating part of it) instead of following the contract above. For
example, `collapse_ranges([4, 7, 8, 9])` currently returns `"4,7"` instead of the correct
`"4,7..9"`. Fix `collapse_ranges` so it follows the contract above for every input, including
when the final run is the one affected.

## Constraints

- Keep the public signature `collapse_ranges(values: list[int]) -> str` unchanged.
- Do not change the behavior of any other function in `rangefmt/core.py`.

## Running the public tests

    python3 -m unittest tests.test_core_public -v
