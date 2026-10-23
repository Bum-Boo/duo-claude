"""CLI-level regression tests for quiz_store.py. Every run uses a temporary HOME; the real home is never touched."""
import datetime as dt, json, os, subprocess, sys, tempfile, unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "quiz_store.py"
TODAY = dt.date.today()


class Base(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.home = self._td.name
        self.store = Path(self.home) / ".claude" / "quiz" / "items.jsonl"
        self.env = {**os.environ, "HOME": self.home, "USERPROFILE": self.home, "PYTHONUTF8": "1"}

    def cli(self, *args, code=None):
        r = subprocess.run([sys.executable, "-X", "utf8", str(SCRIPT), *args], env=self.env,
                           capture_output=True, text=True, encoding="utf-8")
        if code is not None:
            self.assertEqual(r.returncode, code, r.stderr)
        return r

    def add(self, kw, **extra):
        return self.cli("add", json.dumps({"keyword": kw, "question": "q?", **extra}, ensure_ascii=False), code=0)

    def records(self):
        return [json.loads(l) for l in self.store.read_text(encoding="utf-8").splitlines() if l.strip()]

    def seed(self, data: bytes):
        self.store.parent.mkdir(parents=True)
        self.store.write_bytes(data)

    def no_tmp_left(self):
        self.assertEqual([p.name for p in self.store.parent.iterdir() if p.suffix == ".tmp"], [])


class Workflow(Base):
    def test_add_due_grade_stats(self):
        self.add("라이트너 상자", topic="복습")
        self.assertEqual(json.loads(self.cli("due", code=0).stdout), [])  # due tomorrow
        rec = self.records()[0]
        self.assertEqual((rec["box"], rec["seen"], rec["wrong"]), (1, 0, 0))
        self.assertEqual(rec["next"], (TODAY + dt.timedelta(days=1)).isoformat())
        self.assertIn("라이트너 상자", self.store.read_text(encoding="utf-8"))  # not \u-escaped
        # make it due, then walk the boxes
        rec["next"] = TODAY.isoformat()
        self.store.write_text(json.dumps(rec, ensure_ascii=False) + "\n", encoding="utf-8")
        self.assertEqual(json.loads(self.cli("due", code=0).stdout)[0]["keyword"], "라이트너 상자")
        for box, gap in [(2, 3), (3, 7), (4, 14), (5, 30), (5, 30)]:
            self.cli("grade", "라이트너 상자", "right", code=0)
            r = self.records()[0]
            self.assertEqual((r["box"], r["next"]), (box, (TODAY + dt.timedelta(days=gap)).isoformat()))
        self.cli("grade", "라이트너 상자", "wrong", code=0)
        r = self.records()[0]
        self.assertEqual((r["box"], r["seen"], r["wrong"]), (1, 6, 1))
        self.assertEqual(r["next"], (TODAY + dt.timedelta(days=1)).isoformat())
        st = json.loads(self.cli("stats", code=0).stdout)
        self.assertEqual(st, {"total": 1, "due": 0, "weak": [["라이트너 상자", 1]]})

    def test_duplicate_keyword_ignored(self):
        self.add("dup")
        before = self.store.read_bytes()
        self.add("dup", question="different")
        self.assertEqual(self.store.read_bytes(), before)

    def test_due_limit_default_and_n(self):
        for k in "abcdef":
            self.add(k)
        recs = self.records()
        for r in recs:
            r["next"] = TODAY.isoformat()
        self.store.write_text("".join(json.dumps(r) + "\n" for r in recs), encoding="utf-8")
        self.assertEqual(len(json.loads(self.cli("due", code=0).stdout)), 4)
        self.assertEqual(len(json.loads(self.cli("due", "2", code=0).stdout)), 2)
        self.assertEqual(json.loads(self.cli("due", "0", code=0).stdout), [])

    def test_grade_unknown_keyword_does_not_rewrite(self):
        self.add("x")
        before = self.store.read_bytes()
        r = self.cli("grade", "nope", "right", code=0)
        self.assertIn("nope", r.stderr)
        self.assertEqual(self.store.read_bytes(), before)

    def test_readonly_commands_do_not_create_store(self):
        self.cli("due", code=0); self.cli("stats", code=0)
        self.assertFalse(self.store.exists())


class Malformed(Base):
    def assert_rejected(self, *args):
        self.add("keep")
        before = self.store.read_bytes()
        r = self.cli(*args)
        self.assertNotEqual(r.returncode, 0, args)
        self.assertTrue(r.stderr.strip())
        self.assertEqual(self.store.read_bytes(), before)

    def test_bad_add(self):
        for bad in ["not json", "[]", "\"s\"", "{}", '{"keyword": ""}', '{"keyword": 3}', '{"keyword": "  "}']:
            with self.subTest(bad=bad):
                self.assert_rejected("add", bad)
        self.assert_rejected("add")
        self.assert_rejected("add", '{"keyword":"a"}', "extra")

    def test_bad_grade(self):
        for args in [("grade",), ("grade", "keep"), ("grade", "keep", "maybe"), ("grade", "keep", "RIGHT"),
                     ("grade", "keep", "right", "x")]:
            with self.subTest(args=args):
                self.assert_rejected(*args)

    def test_bad_due_and_command(self):
        self.assert_rejected("due", "abc")
        self.assert_rejected("due", "-1")
        self.assert_rejected("frobnicate")

    def test_missing_store_not_created_by_bad_args(self):
        self.assertNotEqual(self.cli("add", "garbage").returncode, 0)
        self.assertNotEqual(self.cli("grade", "k", "bad").returncode, 0)
        self.assertFalse(self.store.exists())


class CorruptStore(Base):
    CASES = {
        "bad json": '{"keyword":"ok","box":1,"next":"2030-01-01","seen":0,"wrong":0}\n{broken\n'.encode(),
        "not object": b'[1,2]\n',
        "missing field": '{"keyword":"k","box":1,"next":"2030-01-01","seen":0}\n'.encode(),
        "bad box": '{"keyword":"k","box":9,"next":"2030-01-01","seen":0,"wrong":0}\n'.encode(),
        "bad date": '{"keyword":"k","box":1,"next":"soon","seen":0,"wrong":0}\n'.encode(),
        "invalid utf8": b'{"keyword":"\xff\xfe"}\n',
    }

    def test_every_command_preserves_bytes_and_explains(self):
        for name, data in self.CASES.items():
            self.seed_fresh(data)
            for args in [("due",), ("stats",), ("add", '{"keyword":"new"}'), ("grade", "k", "right")]:
                with self.subTest(case=name, cmd=args[0]):
                    r = self.cli(*args)
                    self.assertEqual(r.returncode, 1)
                    self.assertIn(str(self.store), r.stderr)
                    self.assertIn("수정되지 않았습니다", r.stderr)
                    self.assertEqual(self.store.read_bytes(), data)
                    self.no_tmp_left()

    def test_error_names_line(self):
        self.seed_fresh(self.CASES["bad json"])
        self.assertIn("2번째 줄", self.cli("stats").stderr)

    def test_blank_lines_and_crlf_tolerated(self):
        rec = '{"keyword":"k","box":2,"next":"2000-01-01","seen":1,"wrong":0}'
        self.seed_fresh(f"\n{rec}\r\n\r\n".encode())
        self.assertEqual(json.loads(self.cli("stats", code=0).stdout)["total"], 1)

    def seed_fresh(self, data):
        if self.store.exists():
            self.store.unlink()
        self.store.parent.mkdir(parents=True, exist_ok=True)
        self.store.write_bytes(data)


class FailedWrite(Base):
    """Run the real script but make a low-level step fail, as a crash/disk-full would."""

    def run_with_fault(self, fault, *args):
        code = ("import os, runpy, sys\n"
                f"{fault}\n"
                f"sys.argv = ['quiz_store.py', *{list(args)!r}]\n"
                f"runpy.run_path({str(SCRIPT)!r}, run_name='__main__')\n")
        return subprocess.run([sys.executable, "-X", "utf8", "-c", code], env=self.env,
                              capture_output=True, text=True, encoding="utf-8")

    def test_failed_replace_or_fsync_keeps_old_store(self):
        self.add("가나다"); self.add("second")
        before = self.store.read_bytes()
        faults = {
            "replace": "def boom(*a, **k): raise OSError('simulated crash before replace')\nos.replace = boom",
            "fsync": "def boom(*a, **k): raise OSError('simulated disk full')\nos.fsync = boom",
        }
        for name, fault in faults.items():
            for args in [("add", '{"keyword":"third"}'), ("grade", "가나다", "right")]:
                with self.subTest(fault=name, cmd=args[0]):
                    r = self.run_with_fault(fault, *args)
                    self.assertNotEqual(r.returncode, 0)
                    self.assertEqual(self.store.read_bytes(), before)
                    self.no_tmp_left()


class Concurrency(Base):
    def test_concurrent_adds_lose_nothing(self):
        n = 16
        with ThreadPoolExecutor(n) as ex:
            rs = list(ex.map(lambda i: self.cli("add", json.dumps({"keyword": f"kw-{i}-한글"}, ensure_ascii=False)), range(n)))
        self.assertEqual([r.returncode for r in rs], [0] * n, [r.stderr for r in rs])
        self.assertEqual(sorted(r["keyword"] for r in self.records()), sorted(f"kw-{i}-한글" for i in range(n)))
        self.no_tmp_left()

    def test_concurrent_duplicate_adds_single_record(self):
        with ThreadPoolExecutor(8) as ex:
            list(ex.map(lambda _: self.cli("add", '{"keyword":"same"}'), range(8)))
        self.assertEqual(len(self.records()), 1)

    def test_concurrent_grades_all_counted(self):
        self.add("g")
        n = 12
        with ThreadPoolExecutor(n) as ex:
            rs = list(ex.map(lambda i: self.cli("grade", "g", "right" if i % 3 else "wrong"), range(n)))
        self.assertEqual([r.returncode for r in rs], [0] * n)
        rec = self.records()[0]
        self.assertEqual(rec["seen"], n)
        self.assertEqual(rec["wrong"], len([i for i in range(n) if i % 3 == 0]))


if __name__ == "__main__":
    unittest.main()
