import unittest

from corvox.clean import chunk, clean, pronounce


class CleanTests(unittest.TestCase):
    def test_strips_markdown_formatting(self):
        text = "# Title\n\n**Bold** and *italic* and `code` and ~~gone~~."
        self.assertEqual(clean(text), "Title.\nBold and italic and code and gone.")

    def test_links_keep_text_and_drop_urls(self):
        text = "See [the docs](https://example.com/x) or https://example.com/raw for more"
        self.assertEqual(clean(text), "See the docs or for more.")

    def test_bullets_get_pauses(self):
        self.assertEqual(clean("- one\n- two\n* three"), "one. two. three.")

    def test_skips_code_blocks_but_reads_the_rest(self):
        text = "Before\n\n```python\nprint('hi')\n```\n\nAfter"
        self.assertEqual(clean(text, skip_code=True), "Before.\nCode block skipped.\nAfter.")

    def test_reads_code_when_asked(self):
        text = "Before\n```\nx = 1\n```"
        self.assertIn("x = 1", clean(text, skip_code=False))
        self.assertNotIn("```", clean(text, skip_code=False))

    def test_unclosed_fence_is_still_skipped(self):
        self.assertEqual(clean("Intro\n```\nhalf a block", skip_code=True), "Intro.\nCode block skipped.")

    def test_tables_are_replaced(self):
        text = "Here:\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\nDone"
        self.assertEqual(clean(text), "Here:\nTable skipped.\nDone.")

    def test_snake_case_survives(self):
        self.assertIn("last_assistant_message", clean("Use last_assistant_message here"))

    def test_emoji_removed(self):
        self.assertEqual(clean("🔊 Done ✅"), "Done.")

    def test_no_length_limit(self):
        text = "Sentence number one. " * 5000
        self.assertGreater(len(clean(text)), 90_000)


class PronounceTests(unittest.TestCase):
    def test_acronyms(self):
        self.assertEqual(pronounce("The API returns JSON."), "The A P I returns jason.")

    def test_plurals(self):
        self.assertEqual(pronounce("two APIs"), "two A P I's")

    def test_whole_words_only(self):
        self.assertEqual(pronounce("macOS and APIKEY and package.json"), "macOS and APIKEY and package.json")

    def test_user_overrides(self):
        self.assertEqual(pronounce("JSON", {"JSON": "jay son"}), "jay son")


class ChunkTests(unittest.TestCase):
    def test_first_chunk_is_short(self):
        parts = chunk("Short one. " * 200)
        self.assertLessEqual(len(parts[0]), 220)
        self.assertTrue(all(len(p) <= 1500 for p in parts))
        self.assertEqual(" ".join(parts).count("Short one."), 200)

    def test_huge_sentence_is_split(self):
        parts = chunk("word " * 2000)
        self.assertTrue(all(len(p) <= 1500 for p in parts))
        self.assertEqual(" ".join(parts).split(), ["word"] * 2000)


if __name__ == "__main__":
    unittest.main()
