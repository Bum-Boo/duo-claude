#!/usr/bin/env python3
"""Leitner-box store for /quiz. Data: ~/.claude/quiz/items.jsonl (one JSON per line)."""
import json, os, sys, time, tempfile, contextlib, datetime as dt
from pathlib import Path

STORE = Path.home() / ".claude" / "quiz" / "items.jsonl"
GAPS = {1: 1, 2: 3, 3: 7, 4: 14, 5: 30}  # box -> days until next review
LOCK_TIMEOUT = 30  # seconds to wait for another add/grade to finish
today = dt.date.today()


class StoreError(Exception):
    pass


def _is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def _check_item(it, n):
    """Validate one stored record; raise StoreError naming the line."""
    where = f"{STORE} {n}번째 줄"
    if not isinstance(it, dict):
        raise StoreError(f"{where}: JSON 객체가 아닙니다.")
    if not isinstance(it.get("keyword"), str) or not it["keyword"]:
        raise StoreError(f"{where}: 'keyword'가 비어 있거나 문자열이 아닙니다.")
    if not _is_int(it.get("box")) or it["box"] not in GAPS:
        raise StoreError(f"{where}: 'box'는 1~5 정수여야 합니다.")
    for f in ("seen", "wrong"):
        if not _is_int(it.get(f)) or it[f] < 0:
            raise StoreError(f"{where}: '{f}'는 0 이상의 정수여야 합니다.")
    try:  # due/stats compare dates lexically, so only canonical YYYY-MM-DD is safe
        ok = dt.date.fromisoformat(it["next"]).isoformat() == it["next"]
    except (KeyError, TypeError, ValueError):
        ok = False
    if not ok:
        raise StoreError(f"{where}: 'next'는 YYYY-MM-DD 형식의 날짜여야 합니다.")


def load():
    if not STORE.exists():
        return []
    try:
        text = STORE.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as e:
        raise StoreError(f"{STORE}: UTF-8로 읽을 수 없습니다 ({e}).")
    items = []
    for n, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            it = json.loads(line)
        except ValueError as e:
            raise StoreError(f"{STORE} {n}번째 줄: JSON 파싱 실패 ({e}).")
        _check_item(it, n)
        items.append(it)
    return items


def save(items):
    """Write to a temp file in the same directory, fsync, then atomically replace."""
    STORE.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=STORE.parent, prefix=STORE.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(json.dumps(i, ensure_ascii=False) for i in items) + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, STORE)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


@contextlib.contextmanager
def locked():
    """Cross-process lock (fcntl on POSIX, msvcrt on Windows) so read-modify-write cycles don't lose records."""
    STORE.parent.mkdir(parents=True, exist_ok=True)
    with open(STORE.parent / (STORE.name + ".lock"), "a+b") as lf:
        if os.name == "nt":
            import msvcrt
            lf.seek(0)
            if not lf.read(1):
                lf.write(b"0"); lf.flush()
            take = lambda: (lf.seek(0), msvcrt.locking(lf.fileno(), msvcrt.LK_NBLCK, 1))
            drop = lambda: (lf.seek(0), msvcrt.locking(lf.fileno(), msvcrt.LK_UNLCK, 1))
        else:
            import fcntl
            take = lambda: fcntl.flock(lf.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            drop = lambda: fcntl.flock(lf.fileno(), fcntl.LOCK_UN)
        deadline = time.monotonic() + LOCK_TIMEOUT
        while True:
            try:
                take()
                break
            except OSError:
                if time.monotonic() > deadline:
                    raise StoreError(f"{LOCK_TIMEOUT}초 동안 저장소 잠금을 얻지 못했습니다. 다른 quiz_store.py 프로세스가 멈췄는지 확인하세요.")
                time.sleep(0.02)
        try:
            yield
        finally:
            with contextlib.suppress(OSError):
                drop()


def usage(msg):
    raise StoreError(f"{msg}\n사용법: quiz_store.py <due [n]|add '<json>'|grade <keyword> <right|wrong>|stats>")


def main():
    argv = sys.argv
    cmd = argv[1] if len(argv) > 1 else "due"
    if cmd == "due":  # print due items as JSON
        n = 4
        if len(argv) > 3:
            usage("due는 [n] 인자 하나까지만 받습니다.")
        if len(argv) > 2:
            try:
                n = int(argv[2])
            except ValueError:
                n = -1
            if n < 0:
                usage(f"due의 개수 인자가 0 이상의 정수가 아닙니다: {argv[2]!r}")
        items = load()
        due = [i for i in items if i["next"] <= today.isoformat()]
        due.sort(key=lambda i: (i["box"], i["next"]))
        print(json.dumps(due[:n], ensure_ascii=False, indent=1))
    elif cmd == "grade":  # grade <keyword> <right|wrong>
        if len(argv) != 4 or argv[3] not in ("right", "wrong"):
            usage("grade에는 <keyword> <right|wrong> 두 인자가 필요합니다.")
        kw, ok = argv[2], argv[3] == "right"
        with locked():
            items = load()
            hit = False
            for i in items:
                if i["keyword"] == kw:
                    hit = True
                    i["box"] = min(i["box"] + 1, 5) if ok else 1
                    i["next"] = (today + dt.timedelta(days=GAPS[i["box"]])).isoformat()
                    i["seen"] += 1
                    i["wrong"] += 0 if ok else 1
            if hit:
                save(items)
            else:
                print(f"경고: keyword {kw!r} 항목이 없어 아무것도 바꾸지 않았습니다.", file=sys.stderr)
    elif cmd == "add":  # add '<json: keyword, question, options, answer, why, topic>' ; box starts at 1, due tomorrow
        if len(argv) != 3:
            usage("add에는 JSON 인자 하나가 필요합니다.")
        try:
            it = json.loads(argv[2])
        except ValueError as e:
            usage(f"add 인자가 올바른 JSON이 아닙니다 ({e}).")
        if not isinstance(it, dict) or not isinstance(it.get("keyword"), str) or not it["keyword"].strip():
            usage("add JSON은 비어 있지 않은 문자열 'keyword'를 가진 객체여야 합니다.")
        with locked():
            items = load()
            if any(i["keyword"] == it["keyword"] for i in items):
                return
            it.update(box=1, next=(today + dt.timedelta(days=1)).isoformat(), seen=0, wrong=0, added=today.isoformat())
            items.append(it)
            save(items)
    elif cmd == "stats":
        if len(argv) != 2:
            usage("stats는 인자를 받지 않습니다.")
        items = load()
        weak = sorted(items, key=lambda i: -i["wrong"])[:5]
        print(json.dumps({"total": len(items), "due": sum(i["next"] <= today.isoformat() for i in items),
                          "weak": [(w["keyword"], w["wrong"]) for w in weak if w["wrong"]]}, ensure_ascii=False))
    else:
        usage(f"알 수 없는 명령: {cmd!r}")


if __name__ == "__main__":
    try:
        main()
    except StoreError as e:
        print(f"quiz_store 오류: {e}\n(저장소 파일은 수정되지 않았습니다.)", file=sys.stderr)
        sys.exit(2 if "사용법" in str(e) else 1)
