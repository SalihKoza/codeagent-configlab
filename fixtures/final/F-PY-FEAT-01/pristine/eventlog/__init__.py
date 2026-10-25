"""eventlog — a small in-memory store of timestamped events with a query API."""

from .store import Event, EventStore

__all__ = ["Event", "EventStore"]
