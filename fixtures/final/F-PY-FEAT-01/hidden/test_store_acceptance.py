import re
import unittest

from eventlog import EventStore

_MISSING_WINDOW_ARG = re.compile(r"query\(\) got an unexpected keyword argument '(start|end)'")


class WindowQueryCase(unittest.TestCase):
    """Calls ``query`` with the new window arguments; a store whose ``query`` does not accept them
    yet fails the test with an assertion (the requested parameters are missing).

    Only the call-site argument-binding error for ``start``/``end`` is converted (no frame of
    ``query`` ran); every other ``TypeError`` propagates unchanged."""

    def q(self, store, *args, **kwargs):
        try:
            return store.query(*args, **kwargs)
        except TypeError as exc:
            if exc.__traceback__.tb_next is None and _MISSING_WINDOW_ARG.search(str(exc)):
                self.fail(f"query() does not accept the time-window arguments: {exc}")
            raise

    def stamps(self, events):
        return [e.timestamp for e in events]


class WindowBoundsTests(WindowQueryCase):
    """Statement "Required behavior" items 1-6 and 9."""

    def setUp(self):
        self.store = EventStore()
        self.events = {t: self.store.record(t, "tick", n=t) for t in (3, 7, 8, 9, 12, 13, 20)}

    def test_window_at_start_included(self):
        # item 1: an event exactly at start is included
        self.assertEqual(self.q(self.store, start=7, end=8), [self.events[7]])

    def test_window_just_after_and_beyond_start(self):
        # item 1 (+ item 4): events immediately after and well after start are included,
        # the event before start is not
        self.assertEqual(self.stamps(self.q(self.store, start=4)), [7, 8, 9, 12, 13, 20])
        self.assertEqual(self.stamps(self.q(self.store, start=8, end=21)), [8, 9, 12, 13, 20])

    def test_window_at_end_excluded(self):
        # item 2: an event exactly at end is excluded; the one just before it is included
        self.assertEqual(self.stamps(self.q(self.store, start=8, end=12)), [8, 9])
        self.assertEqual(self.stamps(self.q(self.store, start=8, end=13)), [8, 9, 12])

    def test_window_start_only(self):
        # items 1, 4: start alone is an inclusive lower bound with no upper bound
        self.assertEqual(self.stamps(self.q(self.store, start=12)), [12, 13, 20])
        self.assertEqual(self.stamps(self.q(self.store, start=12, end=None)), [12, 13, 20])

    def test_window_end_only(self):
        # items 2, 3: end alone is an exclusive upper bound with no lower bound
        self.assertEqual(self.stamps(self.q(self.store, end=9)), [3, 7, 8])
        self.assertEqual(self.stamps(self.q(self.store, start=None, end=9)), [3, 7, 8])

    def test_window_both_bounds(self):
        # items 1, 2: both bounds together
        self.assertEqual(self.stamps(self.q(self.store, start=7, end=13)), [7, 8, 9, 12])
        self.assertEqual(self.stamps(self.q(self.store, start=4, end=20)), [7, 8, 9, 12, 13])

    def test_window_neither_bound_omitted(self):
        # item 9: no bounds -> exactly the unwindowed result
        self.assertEqual(self.q(self.store), self.store.query())
        self.assertEqual(self.stamps(self.q(self.store)), [3, 7, 8, 9, 12, 13, 20])

    def test_window_explicit_none_bounds(self):
        # items 3, 4, 9: both None -> exactly the unwindowed result
        self.assertEqual(self.q(self.store, start=None, end=None), self.store.query())
        self.assertEqual(self.q(self.store, "tick", where={"n": 9}, start=None, end=None),
                         [self.events[9]])

    def test_window_start_equals_end_empty(self):
        # item 5: start == end -> empty, also when an event sits exactly on that timestamp
        self.assertEqual(self.q(self.store, start=8, end=8), [])
        self.assertEqual(self.q(self.store, start=5, end=5), [])

    def test_window_start_after_end_raises(self):
        # item 6: start > end raises ValueError, with or without other filters
        with self.assertRaises(ValueError):
            self.q(self.store, start=13, end=7)
        with self.assertRaises(ValueError):
            self.q(self.store, start=8, end=7)
        with self.assertRaises(ValueError):
            self.q(self.store, "tick", where={"n": 8}, start=9, end=8)
        with self.assertRaises(ValueError):
            self.q(self.store, "nothing-matches", start=9, end=8)

    def test_window_start_after_end_raises_on_empty_store(self):
        # item 6: "regardless of the store's contents"
        with self.assertRaises(ValueError):
            self.q(EventStore(), start=2, end=1)

    def test_window_zero_is_a_bound(self):
        # items 3, 4: only None means "no bound"; 0 is a bound like any other int
        store = EventStore()
        neg, zero, pos = store.record(-4, "tick"), store.record(0, "tick"), store.record(6, "tick")
        self.assertEqual(self.q(store, end=0), [neg])
        self.assertEqual(self.q(store, start=0), [zero, pos])
        self.assertEqual(self.q(store, start=-4, end=0), [neg])
        self.assertEqual(self.q(store, start=0, end=0), [])

    def test_window_values_unrelated_to_example(self):
        # items 1, 2 for arbitrary bounds (no special casing of particular values)
        store = EventStore()
        made = [store.record(t, "tick") for t in range(1000, 1010)]
        self.assertEqual(self.q(store, start=1003, end=1006), made[3:6])
        self.assertEqual(self.q(store, start=1008), made[8:])
        self.assertEqual(self.q(store, end=1002), made[:2])


class WindowWithFiltersTests(WindowQueryCase):
    """Statement items 7 and 8 (window AND existing filters, ordering kept)."""

    def setUp(self):
        s = self.store = EventStore()
        self.e = {
            "a": s.record(10, "login", user="ana", region="eu"),
            "b": s.record(15, "click", user="ana", region="eu"),
            "c": s.record(20, "login", user="bob", region="us"),
            "d": s.record(25, "click", user="bob", region="eu"),
            "f": s.record(30, "login", user="ana", region="us"),
            "g": s.record(35, "login", user="ana", region="eu"),
            "h": s.record(40, "click", user="ana", region="eu"),
        }

    def ids(self, events):
        names = {id(v): k for k, v in self.e.items()}
        return [names[id(e)] for e in events]

    def test_window_with_type_filter(self):
        # item 7: window AND type
        self.assertEqual(self.ids(self.q(self.store, "login", start=15, end=35)), ["c", "f"])
        self.assertEqual(self.ids(self.q(self.store, type="click", start=15)), ["b", "d", "h"])
        self.assertEqual(self.ids(self.q(self.store, "click", end=15)), [])

    def test_window_with_field_filter(self):
        # item 7: window AND where
        self.assertEqual(self.ids(self.q(self.store, where={"user": "ana"}, start=12, end=40)),
                         ["b", "f", "g"])
        self.assertEqual(self.ids(self.q(self.store, where={"region": "us"}, end=30)), ["c"])

    def test_window_with_type_and_several_fields(self):
        # item 7: window AND type AND every where pair
        self.assertEqual(
            self.ids(self.q(self.store, "login", where={"user": "ana", "region": "eu"},
                            start=10, end=40)),
            ["a", "g"])
        self.assertEqual(
            self.ids(self.q(self.store, "login", where={"user": "ana", "region": "eu"},
                            start=11, end=35)),
            [])
        self.assertEqual(
            self.ids(self.q(self.store, "click", where={"user": "ana", "region": "eu"},
                            start=15)),
            ["b", "h"])

    def test_window_keeps_ordering(self):
        # item 8: ascending timestamp, ties in recording order, also for events recorded
        # out of timestamp order
        store = EventStore()
        late1 = store.record(50, "tick", k="x")
        early = store.record(11, "tick", k="x")
        mid1 = store.record(30, "tick", k="x")
        late2 = store.record(50, "tick", k="x")
        mid2 = store.record(30, "tick", k="y")
        before = store.record(5, "tick", k="x")
        mid3 = store.record(30, "tick", k="x")
        self.assertEqual(self.q(store, start=11, end=51), [early, mid1, mid2, mid3, late1, late2])
        self.assertEqual(self.q(store, start=30), [mid1, mid2, mid3, late1, late2])
        self.assertEqual(self.q(store, where={"k": "x"}, end=50), [before, early, mid1, mid3])
        self.assertEqual(self.q(store, "tick", start=6, end=50), [early, mid1, mid2, mid3])

    def test_window_ties_on_bounds(self):
        # items 1, 2, 8: every event exactly at start is included and every event exactly at end
        # is excluded, whatever their number; equal timestamps (on start or inside the window)
        # keep their recording order
        store = EventStore()
        e1 = store.record(40, "tick")
        s1 = store.record(20, "tick")
        m1 = store.record(30, "tick")
        after = store.record(41, "tick")
        s2 = store.record(20, "tick")
        e2 = store.record(40, "tick")
        before = store.record(19, "tick")
        m2 = store.record(30, "tick")
        s3 = store.record(20, "tick")
        self.assertEqual(self.q(store, start=20, end=40), [s1, s2, s3, m1, m2])
        self.assertEqual(self.q(store, start=20, end=30), [s1, s2, s3])
        self.assertEqual(self.q(store, start=30, end=40), [m1, m2])
        self.assertEqual(self.q(store, start=40), [e1, e2, after])
        self.assertEqual(self.q(store, end=20), [before])

    def test_window_on_empty_store(self):
        # items 1-4, 7 on a store without events
        empty = EventStore()
        self.assertEqual(self.q(empty, start=0, end=100), [])
        self.assertEqual(self.q(empty, start=5), [])
        self.assertEqual(self.q(empty, end=5), [])
        self.assertEqual(self.q(empty, "login", where={"user": "ana"}, start=1, end=2), [])

    def test_window_no_events_inside(self):
        # items 1, 2, 7: a window between, before or after all events matches nothing
        self.assertEqual(self.q(self.store, start=16, end=20), [])
        self.assertEqual(self.q(self.store, end=10), [])
        self.assertEqual(self.q(self.store, start=41), [])
        self.assertEqual(self.q(self.store, "login", where={"user": "ana"}, start=11, end=30), [])

    def test_window_returns_new_list(self):
        # item 10: a new list of Events
        first = self.q(self.store, start=10, end=20)
        second = self.q(self.store, start=10, end=20)
        self.assertIsInstance(first, list)
        self.assertIsNot(first, second)
        self.assertEqual(first, second)
        first.clear()
        self.assertEqual(len(self.q(self.store, start=10, end=20)), 2)


if __name__ == "__main__":
    unittest.main()
