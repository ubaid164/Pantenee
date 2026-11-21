import ctypes as c
import os
import unittest
from datetime import date
from pathlib import Path
from queue import SimpleQueue
from tempfile import TemporaryDirectory
from unittest.mock import patch

from win_input import HOTKEYS, HoldKey
from workflows import DEFAULT_PHRASES, match_phrase, run_workflow


class WorkflowTests(unittest.TestCase):
    def test_only_matches_configured_phrase(self):
        self.assertEqual(match_phrase("OPEN DOWNLOADS.", DEFAULT_PHRASES), "downloads")
        self.assertIsNone(match_phrase("Please open downloads", DEFAULT_PHRASES))
        self.assertEqual(match_phrase("ملاحظات کھولو۔", {"note": "ملاحظات کھولو"}), "note")
        self.assertIsNone(match_phrase("open note", {"notes": "open note", "apps": "Open note!"}))

    def test_daily_note_keeps_existing_contents(self):
        with TemporaryDirectory() as folder, patch.object(os, "startfile") as open_file:
            notes = Path(folder)
            note = notes / f"{date.today().isoformat()}.txt"
            run_workflow("note", [], notes)
            self.assertIn("Priorities", note.read_text(encoding="utf-8"))
            note.write_text("Existing note", encoding="utf-8")
            run_workflow("note", [], notes)
            self.assertEqual(note.read_text(encoding="utf-8"), "Existing note")
            open_file.assert_called_with(note)

    def test_work_apps_launch_configured_paths(self):
        with TemporaryDirectory() as folder, patch.object(os, "startfile") as open_file:
            app = Path(folder) / "Work app.lnk"
            app.touch()
            self.assertEqual(run_workflow("apps", [str(app)], Path(folder)), "Opened 1 work app")
            open_file.assert_called_once_with(app)
            with self.assertRaises(ValueError):
                run_workflow("apps", [str(app / "missing.exe")], Path(folder))
            open_file.assert_called_once()

    def test_hotkeys_are_distinct_and_preserve_ctrl_shortcuts(self):
        events = SimpleQueue()
        left, right = HOTKEYS["Left Ctrl"], HOTKEYS["Right Ctrl"]
        hook = HoldKey(events, left, right)
        hook.enabled = True
        with patch("win_input.focused_target", return_value=(1, 2)):
            self.assertFalse(hook.keyboard_event(left, True))
            self.assertEqual(events.get_nowait()[0], "hold")
            hook.keyboard_event(left, False)
            self.assertEqual(events.get_nowait()[0], "release")
            self.assertFalse(hook.keyboard_event(right, True))
            self.assertEqual(events.get_nowait()[0], "workflow_hold")
            self.assertFalse(hook.keyboard_event(ord("C"), True))
            self.assertEqual(events.get_nowait()[0], "cancel")
            hook.keyboard_event(ord("C"), False)
            hook.keyboard_event(right, False)
            self.assertTrue(events.empty())
