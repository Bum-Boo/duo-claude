"""Synthetic reproduction tests for the claude/task-0ft2qm review (docs/cloud-20261031-review.md).

Runs the real CLI in a temporary HOME. Target script comes from QUIZ_STORE_SCRIPT
(default: ../quiz_store.py in this checkout). Legacy stores are produced by
LEGACY_QUIZ_STORE_SCRIPT (default: same as the target) so main -> branch upgrades
can be exercised. Tests assert the *expected* behavior; a failure is a reproduction.
"""
import json, os, subprocess, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET = Path(os.environ.get("QUIZ_STORE_SCRIPT", ROOT / "quiz_store.py"))
LEGACY = Path(os.environ.get("LEGACY_QUIZ_STORE_SCRIPT", TARGET))


class Base(unittest.TestCase):
    def setUp(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        self.home = Path(td.name)
        self.qdir = self.home / ".claude" / "quiz"
        self.store = self.qdir / "items.jsonl"
        self.env = {**os.environ, "HOME": str(self.home), "USERPROFILE": str(self.home)}

    def cli(self, *args, script=TARGET):
        return subprocess.run([sys.executable, "-X", "utf8", str(script), *args], env=self.env,
                              capture_output=True, text=True, encoding="utf-8", errors="replace")


class SymlinkedStore(Base):
    """R1: a symlinked items.jsonl (e.g. pointing into a synced folder) must keep being the link."""

    @unittest.skipIf(os.name == "nt", "symlinks need privileges on Windows")
    def test_write_goes_through_symlink(self):
        target = self.home / "sync" / "items.jsonl"
        target.parent.mkdir()
        target.write_text("", encoding="utf-8")
        self.qdir.mkdir(parents=True)
        self.store.symlink_to(target)
        self.assertEqual(self.cli("add", '{"keyword":"a"}').returncode, 0)
        self.assertTrue(self.store.is_symlink(), "items.jsonl symlink was replaced by a regular file")
        self.assertIn('"a"', target.read_text(encoding="utf-8"))


class UnencodableKeyword(Base):
    """R2: a lone surrogate (valid JSON escape, not encodable as UTF-8)."""

    def test_existing_records_survive(self):
        self.assertEqual(self.cli("add", '{"keyword":"keep"}').returncode, 0)
        before = self.store.read_bytes()
        self.cli("add", '{"keyword":"x\\ud800"}')
        self.assertEqual(self.store.read_bytes(), before)

    def test_rejected_as_usage_error(self):
        self.cli("add", '{"keyword":"keep"}')
        r = self.cli("add", '{"keyword":"x\\ud800"}')
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertNotIn("Traceback", r.stderr)


class LegacyStore(Base):
    """R3: stores written by the legacy script must stay usable after upgrading."""

    def test_normal_legacy_store_round_trips(self):
        for kw in ("라이트너", "b"):
            self.assertEqual(self.cli("add", json.dumps({"keyword": kw, "topic": "t"}, ensure_ascii=False),
                                      script=LEGACY).returncode, 0)
        self.cli("grade", "b", "wrong", script=LEGACY)
        self.assertEqual(json.loads(self.cli("stats").stdout)["total"], 2)
        self.assertEqual(self.cli("grade", "라이트너", "right").returncode, 0)
        self.assertEqual(self.cli("add", '{"keyword":"c"}').returncode, 0)
        self.assertEqual(json.loads(self.cli("stats").stdout)["total"], 3)

    def test_legacy_empty_keyword_record_is_reported_with_line(self):
        """Legacy add accepted {"keyword": ""}; the branch fails closed and must name the line."""
        self.cli("add", '{"keyword":"ok"}', script=LEGACY)
        self.cli("add", '{"keyword":""}', script=LEGACY)
        if len(self.store.read_text(encoding="utf-8").splitlines()) < 2:
            self.skipTest("legacy script already rejects empty keywords")
        r = self.cli("stats")
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertIn("2", r.stderr)


if __name__ == "__main__":
    unittest.main()
