"""Regression tests for the per-agent run-scoped MCP projection lock."""
import threading
import unittest

from run_mcp import _FALLBACK_PROJECTION_LOCK, _projection_lock


class _Agent:
    pass


class ProjectionLockTests(unittest.TestCase):
    def test_same_agent_gets_the_same_reentrant_lock(self):
        agent = _Agent()
        first = _projection_lock(agent)
        self.assertIs(first, _projection_lock(agent))
        with first:
            with first:
                pass

    def test_different_agents_get_independent_locks(self):
        first_agent, second_agent = _Agent(), _Agent()
        self.assertIsNot(_projection_lock(first_agent), _projection_lock(second_agent))

    def test_second_run_blocks_until_first_projection_finishes(self):
        agent = _Agent()
        first_entered = threading.Event()
        release_first = threading.Event()
        second_entered = threading.Event()

        def first():
            with _projection_lock(agent):
                first_entered.set()
                release_first.wait(2)

        def second():
            first_entered.wait(2)
            with _projection_lock(agent):
                second_entered.set()

        t1 = threading.Thread(target=first)
        t2 = threading.Thread(target=second)
        t1.start()
        t2.start()
        try:
            self.assertTrue(first_entered.wait(1))
            self.assertFalse(second_entered.wait(0.2))
            release_first.set()
            self.assertTrue(second_entered.wait(2))
        finally:
            release_first.set()
            t1.join(2)
            t2.join(2)

    def test_non_weakrefable_agent_uses_fallback_lock(self):
        self.assertIs(_projection_lock(1), _FALLBACK_PROJECTION_LOCK)


if __name__ == "__main__":
    unittest.main()
