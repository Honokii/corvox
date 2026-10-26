import json
import os
import tempfile
import unittest
from unittest import mock

from corvox import config, hooks, state


class HookTests(unittest.TestCase):
    """Hook logic against sample payloads, with playback replaced by a recorder."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, {"CORVOX_HOME": self.tmp.name})
        self.env.start()
        self.spoken = []
        self.say = mock.patch("corvox.speech.spool.enqueue",
                              side_effect=lambda text, **kw: self.spoken.append(text))
        self.say.start()

    def tearDown(self):
        self.say.stop()
        self.env.stop()
        self.tmp.cleanup()

    def prompt(self, agent, text, session="s1"):
        out = hooks.handle(agent, "prompt", json.dumps({"prompt": text, "session_id": session}))
        return json.loads(out) if out else None

    def stop(self, agent, reply, session="s1"):
        out = hooks.handle(agent, "stop", json.dumps({"last_assistant_message": reply, "session_id": session}))
        return json.loads(out)

    def test_silent_by_default(self):
        self.prompt("claude", "fix the bug")
        self.assertEqual(self.stop("claude", "Fixed it."), {})
        self.assertEqual(self.spoken, [])

    def test_marker_reads_that_reply_only(self):
        self.prompt("codex", "🔊 explain this")
        self.stop("codex", "It does X.")
        self.prompt("codex", "and now?")
        self.stop("codex", "Now Y.")
        self.assertEqual(self.spoken, ["It does X."])

    def test_marker_phrase_is_case_insensitive(self):
        self.prompt("claude", "Summarize and READ ALOUD please")
        self.stop("claude", "Summary.")
        self.assertEqual(self.spoken, ["Summary."])

    def test_toggle_command_is_blocked_and_applies_to_both_agents(self):
        result = self.prompt("claude", "corvox on")
        self.assertEqual(result["decision"], "block")
        self.assertTrue(state.auto_read())
        self.prompt("codex", "anything")
        self.stop("codex", "Codex reply.")
        self.assertEqual(self.spoken, ["Codex reply."])
        self.prompt("codex", "/corvox-off")
        self.assertFalse(state.auto_read())

    def test_last_reads_saved_reply(self):
        self.prompt("claude", "hi")
        self.stop("claude", "Earlier answer.")
        result = self.prompt("codex", "corvox last")
        self.assertIn("claude", result["reason"])
        self.assertEqual(self.spoken, ["Earlier answer."])

    def test_direct_reading_is_not_talked_over(self):
        state.set_auto_read(True)
        self.prompt("claude", "read this file to me")
        state.note_direct_speech()  # what `corvox say` records when the agent runs it
        self.stop("claude", "I read the file to you.")
        self.assertEqual(self.spoken, [])

    def test_bad_payload_never_raises(self):
        self.assertEqual(hooks.handle("codex", "stop", "not json"), "{}")
        self.assertEqual(hooks.handle("claude", "prompt", "not json"), "")

    def test_transcript_fallback(self):
        path = os.path.join(self.tmp.name, "t.jsonl")
        with open(path, "w", encoding="utf-8") as f:
            f.write(json.dumps({"type": "user", "message": {"content": "q"}}) + "\n")
            f.write(json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "From transcript."}]}}) + "\n")
        state.set_auto_read(True)
        hooks.handle("claude", "stop", json.dumps({"transcript_path": path, "session_id": "s1"}))
        self.assertEqual(self.spoken, ["From transcript."])


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, {"CORVOX_HOME": self.tmp.name})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_template_matches_defaults(self):
        config.init()
        self.assertEqual(config.load(), config.DEFAULTS)

    def test_set_keeps_comments(self):
        config.set_value("speed", "1.25")
        config.set_value("skip_code", "off")
        text = (config.paths.config_file()).read_text(encoding="utf-8")
        self.assertIn("# 1.0 = normal", text)
        self.assertEqual(config.load()["speed"], 1.25)
        self.assertFalse(config.load()["skip_code"])

    def test_rejects_bad_values(self):
        with self.assertRaises(ValueError):
            config.set_value("engine", "loud")
        with self.assertRaises(KeyError):
            config.set_value("nope", "1")


if __name__ == "__main__":
    unittest.main()
