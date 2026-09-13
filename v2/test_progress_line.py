import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

V2_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(V2_DIR))

from red_gym_env_v2 import (
    PROGRESS_PRINT_N,
    RedGymEnv,
    format_progress_line,
    should_print_progress,
)


def _stats(**overrides):
    base = {
        "step": 0,
        "map": 40,
        "badge": 0,
        "max_map_progress": 0,
        "unique_maps": 1,
        "event": 0.0,
        "dex_seen": 0,
        "levels_sum": 5,
    }
    base.update(overrides)
    return base


class ShouldPrintProgressTest(unittest.TestCase):
    def test_first_line_when_last_is_none(self):
        self.assertTrue(should_print_progress(None, _stats()))

    def test_same_fields_before_n_is_false(self):
        last = _stats(step=0)
        current = _stats(step=PROGRESS_PRINT_N - 1)
        self.assertFalse(should_print_progress(last, current))

    def test_n_step_tick(self):
        last = _stats(step=0)
        current = _stats(step=PROGRESS_PRINT_N)
        self.assertTrue(should_print_progress(last, current))

    def test_map_change_before_n(self):
        last = _stats(step=0, map=40)
        current = _stats(step=1, map=12)
        self.assertTrue(should_print_progress(last, current))

    def test_badge_change_before_n(self):
        last = _stats(step=10, badge=0)
        current = _stats(step=11, badge=1)
        self.assertTrue(should_print_progress(last, current))

    def test_mmp_change_before_n(self):
        last = _stats(step=10, max_map_progress=0)
        current = _stats(step=11, max_map_progress=1)
        self.assertTrue(should_print_progress(last, current))

    def test_reset_last_none_does_not_skip_first_line(self):
        after_reset = None
        first_of_episode = _stats(step=0, map=40, badge=0, max_map_progress=0)
        self.assertTrue(should_print_progress(after_reset, first_of_episode))


class FormatProgressLineTest(unittest.TestCase):
    def test_minimum_fields_and_mmp_label(self):
        line = format_progress_line(_stats(
            step=128,
            map=12,
            max_map_progress=3,
            unique_maps=4,
            badge=1,
            event=4.0,
            dex_seen=7,
            levels_sum=22,
        ))
        self.assertEqual(
            line,
            "step: 128 map: 12 mmp: 3 unique_maps: 4 badge: 1 "
            "event: 4.0 dex_seen: 7 levels_sum: 22",
        )


class DummyEnv:
    maybe_print_progress = RedGymEnv.maybe_print_progress


class MaybePrintProgressTest(unittest.TestCase):
    def test_debug_false_is_silent(self):
        env = DummyEnv()
        env.debug = False
        env.agent_stats = [_stats(step=0)]
        env._last_progress_print = None
        buf = io.StringIO()
        with redirect_stdout(buf):
            env.maybe_print_progress()
        self.assertEqual(buf.getvalue(), "")
        self.assertIsNone(env._last_progress_print)

    def test_debug_true_prints_cr_line_and_updates_last(self):
        env = DummyEnv()
        env.debug = True
        env.agent_stats = [_stats(step=0)]
        env._last_progress_print = None
        buf = io.StringIO()
        with redirect_stdout(buf):
            env.maybe_print_progress()
        out = buf.getvalue()
        self.assertTrue(out.startswith("\rstep: 0 "))
        self.assertEqual(
            env._last_progress_print,
            {"step": 0, "map": 40, "badge": 0, "max_map_progress": 0},
        )

    def test_no_reprint_until_n_or_change(self):
        env = DummyEnv()
        env.debug = True
        env.agent_stats = [_stats(step=0)]
        env._last_progress_print = None
        with redirect_stdout(io.StringIO()):
            env.maybe_print_progress()
        env.agent_stats = [_stats(step=1)]
        buf = io.StringIO()
        with redirect_stdout(buf):
            env.maybe_print_progress()
        self.assertEqual(buf.getvalue(), "")
        env.agent_stats = [_stats(step=2, badge=1)]
        buf = io.StringIO()
        with redirect_stdout(buf):
            env.maybe_print_progress()
        self.assertIn("badge: 1", buf.getvalue())


class ConfigDebugDefaultTest(unittest.TestCase):
    def test_missing_debug_key_defaults_false(self):
        config = {"print_rewards": True}
        self.assertFalse(config.get("debug", False))


if __name__ == "__main__":
    unittest.main()
