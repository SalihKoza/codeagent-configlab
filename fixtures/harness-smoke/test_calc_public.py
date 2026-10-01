"""Public smoke test shipped inside the fixture (the agent may see this).

Hidden acceptance/regression tests are NOT here — they would live outside the agent-visible
boundary. This only exercises the public behavior.
"""

from calc import add


def test_add():
    assert add(2, 3) == 5
