"""Unit tests for interactive feature selector in apply_patch.py."""

import unittest
from unittest.mock import patch
from apply_patch import interactive_feature_selector, AVAILABLE_PATCHES


class TestInteractiveFeatureSelector(unittest.TestCase):
    def test_toggle_off_one_feature(self):
        """User enters '1' to disable Level Cap, then presses Enter to confirm."""
        # 1 toggles 'level-cap' off, '' confirms
        with patch("builtins.input", side_effect=["1", ""]):
            selected = interactive_feature_selector(AVAILABLE_PATCHES)

        self.assertNotIn("level-cap", selected)
        self.assertIn("first-encounter", selected)
        self.assertIn("permadeath", selected)
        self.assertIn("starter-by-tid", selected)
        self.assertEqual(len(selected), 3)

    def test_toggle_multiple_features(self):
        """User toggles off features 1 and 3, then confirms."""
        with patch("builtins.input", side_effect=["1", "3", ""]):
            selected = interactive_feature_selector(AVAILABLE_PATCHES)

        self.assertNotIn("level-cap", selected)
        self.assertNotIn("permadeath", selected)
        self.assertEqual(selected, ["first-encounter", "starter-by-tid"])

    def test_deselect_all_then_enable_one(self):
        """User types 'n' (none), then '2' (first-encounter), then confirms."""
        with patch("builtins.input", side_effect=["n", "2", ""]):
            selected = interactive_feature_selector(AVAILABLE_PATCHES)

        self.assertEqual(selected, ["first-encounter"])

    def test_deselect_all_then_select_all(self):
        """User types 'n' (none), then 'a' (all), then confirms."""
        with patch("builtins.input", side_effect=["n", "a", ""]):
            selected = interactive_feature_selector(AVAILABLE_PATCHES)

        self.assertEqual(selected, list(AVAILABLE_PATCHES.keys()))

    def test_prevent_empty_selection(self):
        """If user deselects all ('n') and hits Enter, menu refuses and prompts until valid."""
        with patch("builtins.input", side_effect=["n", "", "4", ""]):
            selected = interactive_feature_selector(AVAILABLE_PATCHES)

        self.assertEqual(selected, ["starter-by-tid"])


if __name__ == "__main__":
    unittest.main()
