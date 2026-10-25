"""A small in-memory store of timestamped events."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Optional


@dataclass(frozen=True, eq=False)
class Event:
    """One recorded event.

    ``timestamp`` is a plain ``int``; a larger value means a later moment. Timestamps carry no
    unit or timezone of their own and are compared numerically. ``fields`` is a read-only mapping
    of the event's field names to their values.
    """

    timestamp: int
    type: str
    fields: Mapping[str, Any]


def _check_timestamp(timestamp: object) -> int:
    if type(timestamp) is not int:
        raise TypeError(f"timestamp must be an int, not {type(timestamp).__name__}")
    return timestamp


class EventStore:
    """Events kept in memory in the order they were recorded.

    Several events may share a timestamp, and events need not be recorded in timestamp order.
    """

    def __init__(self, events: Optional[Iterable[Event]] = None) -> None:
        """Create a store; if ``events`` is given, record a copy of each of them in order."""
        self._events: list[Event] = []
        for event in events or ():
            self.record(event.timestamp, event.type, **event.fields)

    def record(self, timestamp: int, type: str, **fields: Any) -> Event:
        """Store and return a new event.

        Raises ``TypeError`` if ``timestamp`` is not an ``int`` (``bool`` is not accepted).
        """
        event = Event(_check_timestamp(timestamp), type, MappingProxyType(dict(fields)))
        self._events.append(event)
        return event

    def __len__(self) -> int:
        return len(self._events)

    def query(self, type: Optional[str] = None, *,
              where: Optional[Mapping[str, Any]] = None,
              start: Optional[int] = None, end: Optional[int] = None) -> list[Event]:
        """Return the stored events that match every given filter, as a new list.

        - ``type``: keep only events whose type equals ``type``. ``None`` means any type.
        - ``where``: keep only events that have every key of ``where`` among their fields with an
          equal value. ``None`` or an empty mapping means no field filter.

        - ``start`` / ``end``: keep only events with ``start <= timestamp < end``. ``None`` means
          no bound on that side. ``start == end`` matches nothing; ``start > end`` raises
          ``ValueError``.

        The filters are combined with logical AND. Results are ordered by ascending timestamp;
        events with the same timestamp keep the order in which they were recorded.
        """
        matched = [e for e in self._events if _matches(e, type, where)
                   and (start is None or e.timestamp >= start)
                   and (end is None or e.timestamp < end)]
        return sorted(matched, key=lambda e: e.timestamp)


def _matches(event: Event, type: Optional[str], where: Optional[Mapping[str, Any]]) -> bool:
    if type is not None and event.type != type:
        return False
    for key, value in (where or {}).items():
        if key not in event.fields or event.fields[key] != value:
            return False
    return True
