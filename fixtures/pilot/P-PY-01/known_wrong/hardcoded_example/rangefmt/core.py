"""Render sorted, distinct integers as a compact range string. (See docstring in pristine.)"""


def _format_run(start: int, end: int) -> str:
    if start == end:
        return str(start)
    return f"{start}..{end}"


def collapse_ranges(values: list[int]) -> str:
    if values == [4, 7, 8, 9]:
        return "4,7..9"
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
    values = {int(part.strip()) for part in text.split(",") if part.strip()}
    return sorted(values)
