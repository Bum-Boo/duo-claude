#!/usr/bin/env python3
"""Leitner-box store for /quiz. Data: ~/.claude/quiz/items.jsonl (one JSON per line)."""
import json, sys, datetime as dt
from pathlib import Path

STORE = Path.home() / ".claude" / "quiz" / "items.jsonl"
GAPS = {1: 1, 2: 3, 3: 7, 4: 14, 5: 30}  # box -> days until next review
today = dt.date.today()


def load():
    if not STORE.exists():
        return []
    return [json.loads(l) for l in STORE.read_text(encoding="utf-8").splitlines() if l.strip()]


def save(items):
    STORE.parent.mkdir(parents=True, exist_ok=True)
    STORE.write_text("\n".join(json.dumps(i, ensure_ascii=False) for i in items) + "\n", encoding="utf-8")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "due"
    items = load()
    if cmd == "due":  # print due items as JSON
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 4
        due = [i for i in items if i["next"] <= today.isoformat()]
        due.sort(key=lambda i: (i["box"], i["next"]))
        print(json.dumps(due[:n], ensure_ascii=False, indent=1))
    elif cmd == "grade":  # grade <keyword> <right|wrong>  (adds the item first if given via add)
        kw, ok = sys.argv[2], sys.argv[3] == "right"
        for i in items:
            if i["keyword"] == kw:
                i["box"] = min(i["box"] + 1, 5) if ok else 1
                i["next"] = (today + dt.timedelta(days=GAPS[i["box"]])).isoformat()
                i["seen"] += 1
                i["wrong"] += 0 if ok else 1
        save(items)
    elif cmd == "add":  # add '<json: keyword, question, options, answer, why, topic>' ; box starts at 1, due tomorrow
        it = json.loads(sys.argv[2])
        if any(i["keyword"] == it["keyword"] for i in items):
            return
        it.update(box=1, next=(today + dt.timedelta(days=1)).isoformat(), seen=0, wrong=0, added=today.isoformat())
        items.append(it)
        save(items)
    elif cmd == "stats":
        weak = sorted(items, key=lambda i: -i["wrong"])[:5]
        print(json.dumps({"total": len(items), "due": sum(i["next"] <= today.isoformat() for i in items),
                          "weak": [(w["keyword"], w["wrong"]) for w in weak if w["wrong"]]}, ensure_ascii=False))


main()
