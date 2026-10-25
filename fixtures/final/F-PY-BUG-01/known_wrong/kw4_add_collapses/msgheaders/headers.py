"""An ordered collection of message headers."""

from __future__ import annotations

from typing import Iterable, Iterator, Optional


def _same_name(a: str, b: str) -> bool:
    return a.lower() == b.lower()


class Headers:
    """Message headers stored as ``(name, value)`` entries in insertion order.

    Header names are ASCII strings and are compared case-insensitively: ``"Content-Type"``,
    ``"content-type"`` and ``"CONTENT-TYPE"`` all name the same header. Two names match only if
    they are equal ignoring case. The collection may hold several entries for the same header.
    Each entry keeps the name spelling it was stored with.
    """

    def __init__(self, items: Optional[Iterable[tuple[str, str]]] = None) -> None:
        self._entries: list[tuple[str, str]] = []
        for name, value in items or ():
            self.add(name, value)

    def add(self, name: str, value: str) -> None:
        """Append a ``(name, value)`` entry. Existing entries for ``name`` are kept."""
        self.set(name, value)

    def set(self, name: str, value: str) -> None:
        """Replace every entry for header ``name`` with a single ``(name, value)`` entry.

        All existing entries whose name matches ``name`` are removed and one new entry, spelled
        exactly as ``name``, is appended at the end of the collection. The other entries keep
        their relative order. If no entry matches, the new entry is simply appended.
        """
        kept = [(n, v) for n, v in self._entries if not _same_name(n, name)]
        kept.append((name, value))
        self._entries = kept

    def get(self, name: str, default: Optional[str] = None) -> Optional[str]:
        """Value of the first entry for ``name``, or ``default`` if there is none."""
        for n, v in self._entries:
            if _same_name(n, name):
                return v
        return default

    def get_all(self, name: str) -> list[str]:
        """Values of all entries for ``name``, in collection order (empty list if none)."""
        return [v for n, v in self._entries if _same_name(n, name)]

    def items(self) -> list[tuple[str, str]]:
        """A new list of all ``(name, value)`` entries, in collection order."""
        return list(self._entries)

    def __iter__(self) -> Iterator[tuple[str, str]]:
        return iter(list(self._entries))

    def __len__(self) -> int:
        return len(self._entries)

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and any(_same_name(n, name) for n, _ in self._entries)
