import unittest

from app.ui_shell_preview import DEFAULT_SHELL_STATE, normalize_shell_state


class UiShellStateTest(unittest.TestCase):
    def test_invalid_persisted_values_return_to_safe_bounds(self):
        state = normalize_shell_state(
            {
                "theme": "purple",
                "section": "Missing",
                "sidebar_width": 999,
                "inspector_width": 1,
            }
        )
        self.assertEqual(state["theme"], DEFAULT_SHELL_STATE["theme"])
        self.assertEqual(state["section"], DEFAULT_SHELL_STATE["section"])
        self.assertEqual(state["sidebar_width"], 280)
        self.assertEqual(state["inspector_width"], 240)

    def test_history_view_state_is_normalized(self):
        state = normalize_shell_state(
            {"history_filter": "transcricao", "history_sort": "name", "history_scroll": 2.0}
        )
        self.assertEqual(state["history_filter"], "transcricao")
        self.assertEqual(state["history_sort"], "name")
        self.assertEqual(state["history_scroll"], 1.0)


if __name__ == "__main__":
    unittest.main()
