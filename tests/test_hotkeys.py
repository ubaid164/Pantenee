import unittest
from queue import SimpleQueue
from unittest.mock import patch

from win_input import HOTKEYS, HoldKey


class HotkeyTests(unittest.TestCase):
    @patch("win_input.focused_target", return_value=(1, 2))
    def test_only_the_selected_key_starts_dictation(self, _focus):
        events = SimpleQueue()
        left, right = HOTKEYS["Left Ctrl"], HOTKEYS["Right Ctrl"]
        hook = HoldKey(events, left)
        hook.enabled = True

        self.assertFalse(hook.keyboard_event(right, True))
        self.assertFalse(hook.keyboard_event(right, False))
        self.assertTrue(events.empty())

        hook.key = right
        self.assertFalse(hook.keyboard_event(right, True))
        self.assertFalse(hook.keyboard_event(right, False))
        self.assertEqual(events.get_nowait()[0], "hold")
        self.assertEqual(events.get_nowait()[0], "release")
        self.assertTrue(events.empty())

    @patch("win_input.focused_target", return_value=(1, 2))
    def test_control_shortcut_cancels_dictation(self, _focus):
        events = SimpleQueue()
        key = HOTKEYS["Left Ctrl"]
        hook = HoldKey(events, key)
        hook.enabled = True

        self.assertFalse(hook.keyboard_event(key, True))
        self.assertEqual(events.get_nowait()[0], "hold")
        self.assertFalse(hook.keyboard_event(ord("C"), True))
        self.assertEqual(events.get_nowait()[0], "cancel")
        hook.keyboard_event(ord("C"), False)
        hook.keyboard_event(key, False)
        self.assertTrue(events.empty())
