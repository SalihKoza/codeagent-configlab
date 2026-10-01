"""Render sorted, distinct integers as a compact range string.

collapse_ranges(values) takes a list of integers in strictly ascending order, with no
duplicates (it may be empty; it may contain negative integers) and returns a string:

- split the input into maximal runs of consecutive integers;
- a run of one integer n renders as str(n);
- a run of two or more integers from start to end renders as f"{start}..{end}"
  (this applies even when the run has exactly two integers);
- runs are joined with "," in input order; an empty input returns "".

parse_int_list(text) is a small helper used elsewhere in this package: it parses a
comma-separated string of integers into a sorted list of distinct ints.
"""


def _format_run(start: int, end: int) -> str:
    if start == end:
        return str(start)
    return f"{start}..{end}"


def collapse_ranges(values: list[int]) -> str:
    if not values:
        return ""
    parts = []
    start = end = values[0]
    for v in values[1:]:
        if v == end + 1:
            end = v
        else:
            parts.append(_format_run(start, end))
            start = end = v
    parts.append(str(start))
    return ",".join(parts)


def parse_int_list(text: str) -> list[int]:
    """Parse a comma-separated string of integers into a sorted list of distinct ints."""
    values = {int(part.strip()) for part in text.split(",") if part.strip()}
    return sorted(values)
