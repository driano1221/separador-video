import unittest

from app.ui_theme import TokenTheme, validate_tokens
from app.ui_tokens import COMPONENT, PRIMITIVES, SEMANTIC


class UiTokensTest(unittest.TestCase):
    def test_every_alias_resolves_in_both_themes(self):
        validate_tokens()

    def test_component_layers_have_no_raw_visual_values(self):
        aliases = set(PRIMITIVES) | set.intersection(*(set(theme) for theme in SEMANTIC.values()))
        self.assertTrue(all(value in aliases for value in COMPONENT.values()))

    def test_dark_and_light_use_different_base_surfaces(self):
        self.assertNotEqual(TokenTheme("dark").get("surface.base"), TokenTheme("light").get("surface.base"))


if __name__ == "__main__":
    unittest.main()
