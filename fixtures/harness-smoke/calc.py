"""Harness smoke fixture — trivial, no research value, NOT a benchmark task.

Exists only so the harness skeleton has something to copy, hash, evaluate and clean up. The
smoke "feature" a dry agent may add is ``multiply``; the smoke regression is that ``add`` keeps
working. There are no hidden tests and no reference solution here.
"""


def add(a, b):
    return a + b
