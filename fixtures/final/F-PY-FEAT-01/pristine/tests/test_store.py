import unittest

from eventlog import Event, EventStore


class EventStoreTests(unittest.TestCase):
    def setUp(self):
        self.store = EventStore()
        self.login = self.store.record(10, "login", user="ana")
        self.click = self.store.record(20, "click", user="ana", button="save")
        self.logout = self.store.record(30, "logout", user="ana")

    def test_record_returns_event(self):
        self.assertIsInstance(self.login, Event)
        self.assertEqual((self.login.timestamp, self.login.type), (10, "login"))
        self.assertEqual(dict(self.login.fields), {"user": "ana"})
        self.assertEqual(len(self.store), 3)

    def test_record_rejects_non_int_timestamp(self):
        with self.assertRaises(TypeError):
            self.store.record("10", "login")

    def test_query_everything(self):
        self.assertEqual(self.store.query(), [self.login, self.click, self.logout])

    def test_query_by_type(self):
        self.assertEqual(self.store.query("click"), [self.click])
        self.assertEqual(self.store.query("missing"), [])

    def test_query_by_field(self):
        self.assertEqual(self.store.query(where={"button": "save"}), [self.click])
        self.assertEqual(self.store.query(where={"user": "bob"}), [])

    def test_query_type_and_field(self):
        self.assertEqual(self.store.query("click", where={"user": "ana"}), [self.click])
        self.assertEqual(self.store.query("login", where={"button": "save"}), [])

    def test_query_orders_by_timestamp(self):
        store = EventStore()
        late = store.record(5, "ping")
        early = store.record(1, "ping")
        same = store.record(5, "ping")
        self.assertEqual(store.query(), [early, late, same])

    def test_query_returns_list(self):
        result = self.store.query()
        self.assertIsInstance(result, list)
        self.assertIsNot(result, self.store.query())


if __name__ == "__main__":
    unittest.main()
