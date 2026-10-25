import inspect
import unittest

from eventlog import Event, EventStore


class UnwindowedQueryRegressionTests(unittest.TestCase):
    """Behavior that must stay as it is (statement items 9-10, Constraints, query docstring)."""

    def setUp(self):
        s = self.store = EventStore()
        self.e1 = s.record(40, "deploy", service="api", env="prod")
        self.e2 = s.record(10, "build", service="api")
        self.e3 = s.record(25, "deploy", service="web", env="staging")
        self.e4 = s.record(10, "deploy", service="api", env="prod")
        self.e5 = s.record(55, "build", service="web", env=None)

    def test_unwindowed_query_returns_everything_sorted(self):
        # item 9; docstring ordering: ascending timestamp, ties in recording order
        self.assertEqual(self.store.query(), [self.e2, self.e4, self.e3, self.e1, self.e5])

    def test_unwindowed_type_filter(self):
        # item 10: type keeps events whose type equals it
        self.assertEqual(self.store.query("deploy"), [self.e4, self.e3, self.e1])
        self.assertEqual(self.store.query(type="build"), [self.e2, self.e5])
        self.assertEqual(self.store.query("Deploy"), [])
        self.assertEqual(self.store.query(None), self.store.query())

    def test_unwindowed_field_filter(self):
        # item 10: every where key present with an equal value; missing field never matches
        self.assertEqual(self.store.query(where={"service": "web"}), [self.e3, self.e5])
        self.assertEqual(self.store.query(where={"env": "prod"}), [self.e4, self.e1])
        self.assertEqual(self.store.query(where={"env": None}), [self.e5])
        self.assertEqual(self.store.query(where={"region": "eu"}), [])
        self.assertEqual(self.store.query(where={"service": "api", "env": "prod"}),
                         [self.e4, self.e1])

    def test_unwindowed_empty_where_matches_all(self):
        # query docstring: None or an empty mapping means no field filter
        self.assertEqual(self.store.query(where={}), self.store.query())
        self.assertEqual(self.store.query("build", where={}), [self.e2, self.e5])

    def test_unwindowed_filter_conjunction(self):
        # item 10 / docstring: filters combined with logical AND
        self.assertEqual(self.store.query("deploy", where={"service": "api"}), [self.e4, self.e1])
        self.assertEqual(self.store.query("build", where={"env": "prod"}), [])
        self.assertEqual(self.store.query("deploy", where={"service": "web", "env": "prod"}), [])
        self.assertEqual(self.store.query("deploy", where={"service": "web", "env": "staging"}),
                         [self.e3])

    def test_unwindowed_ordering_deterministic(self):
        # item 8 / docstring: same result on every call; ties keep recording order
        store = EventStore()
        made = [store.record(t, "x", i=i) for i, t in enumerate([3, 1, 3, 2, 1, 3])]
        expected = [made[1], made[4], made[3], made[0], made[2], made[5]]
        for _ in range(3):
            self.assertEqual(store.query(), expected)
        self.assertEqual(store.query("x"), expected)

    def test_unwindowed_return_type_is_new_list(self):
        # item 10: a new list of Events
        first, second = self.store.query(), self.store.query()
        self.assertIsInstance(first, list)
        self.assertTrue(all(isinstance(e, Event) for e in first))
        self.assertIsNot(first, second)
        first.clear()
        self.assertEqual(len(self.store.query()), 5)

    def test_unwindowed_empty_store(self):
        store = EventStore()
        self.assertEqual(store.query(), [])
        self.assertEqual(store.query("deploy", where={"env": "prod"}), [])
        self.assertEqual(len(store), 0)


class ExistingApiRegressionTests(unittest.TestCase):
    """Public API outside the new optional parameters (Constraints, docstrings)."""

    def test_existing_record_returns_event(self):
        store = EventStore()
        e = store.record(7, "ping", host="a", ok=True)
        self.assertIsInstance(e, Event)
        self.assertEqual((e.timestamp, e.type, dict(e.fields)), (7, "ping", {"host": "a", "ok": True}))
        self.assertEqual(store.query(), [e])
        self.assertEqual(len(store), 1)

    def test_existing_record_rejects_non_int_timestamps(self):
        store = EventStore()
        for bad in ("7", 7.0, True, None):
            with self.assertRaises(TypeError):
                store.record(bad, "ping")
        self.assertEqual(len(store), 0)

    def test_existing_constructor_copies_events(self):
        source = EventStore()
        a = source.record(2, "b", k=1)
        b = source.record(1, "a")
        copy = EventStore(source.query())
        self.assertEqual(len(copy), 2)
        self.assertEqual([(e.timestamp, e.type, dict(e.fields)) for e in copy.query()],
                         [(1, "a", {}), (2, "b", {"k": 1})])
        self.assertEqual(source.query(), [b, a])

    def test_existing_query_parameters_unchanged(self):
        # Constraints: type (positional-or-keyword, default None) and keyword-only where
        # (default None) keep their names, kinds and defaults
        params = inspect.signature(EventStore.query).parameters
        self.assertEqual(list(params)[:2], ["self", "type"])
        self.assertEqual(params["type"].kind, inspect.Parameter.POSITIONAL_OR_KEYWORD)
        self.assertIsNone(params["type"].default)
        self.assertEqual(params["where"].kind, inspect.Parameter.KEYWORD_ONLY)
        self.assertIsNone(params["where"].default)


if __name__ == "__main__":
    unittest.main()
