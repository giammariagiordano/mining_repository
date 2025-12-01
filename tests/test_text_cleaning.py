import unittest
from utils.text_utils import clean_text_for_json

class TestTextCleaning(unittest.TestCase):
    def test_basic_cleaning(self):
        text = "Hello, World! 123"
        expected = "Hello World 123"
        self.assertEqual(clean_text_for_json(text), expected)

    def test_special_characters(self):
        text = "User@Name #Issue:123"
        expected = "User Name Issue 123"
        self.assertEqual(clean_text_for_json(text), expected)

    def test_multiple_spaces(self):
        text = "Too   many    spaces"
        expected = "Too many spaces"
        self.assertEqual(clean_text_for_json(text), expected)

    def test_newlines_and_tabs(self):
        text = "Line1\nLine2\tTabbed"
        expected = "Line1 Line2 Tabbed"
        self.assertEqual(clean_text_for_json(text), expected)

    def test_empty_input(self):
        self.assertEqual(clean_text_for_json(""), "")
        self.assertEqual(clean_text_for_json(None), "")

    def test_code_snippet(self):
        text = "def foo(): return 1"
        expected = "def foo return 1"
        self.assertEqual(clean_text_for_json(text), expected)

if __name__ == '__main__':
    unittest.main()
