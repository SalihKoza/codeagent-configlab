# eventlog

A small in-memory store of timestamped events. Timestamps are plain integers (a larger value is
later); events can be queried by type and by field values.

Run the public tests:

    python3 -m unittest tests.test_store -v
