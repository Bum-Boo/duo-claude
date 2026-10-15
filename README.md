# duo-claude

**English** | [한국어](README.ko.md) | [日本語](README.ja.md) | [中文](README.zh-CN.md)

Duolingo-style review for Claude Code. After Claude finishes a chunk of work, it quizzes you with 4-choice questions on the keywords from that work, and brings back the ones you got wrong on a spaced-repetition schedule. Questions are written in Korean.

## Install

```sh
git clone https://github.com/Bum-Boo/duo-claude ~/.claude/skills/duo-claude
```

Requires Python 3 (standard library only). Restart Claude Code so the skill is picked up.

## Use

| Command | What it does |
| --- | --- |
| `/duo-claude` | Turn on. Quizzes now on the session's work, then after each finished chunk of work (1-2 questions). |
| `/duo-claude off` | Turn off for the session. |
| `/duo-claude wiki [keyword]` | Quiz from your own wiki/notes instead of the code. Needs a note search/read tool (e.g. a wiki MCP) or a notes folder you point it to. |
| `/duo-claude review` | Only items that are due for review. |
| `/duo-claude stats` | Totals, items due, most-missed keywords. |

It never interrupts work mid-task and skips trivial edits. The on/off state lives in the conversation only, so re-run `/duo-claude` in a new session.

## How review works

Items are stored in `~/.claude/quiz/items.jsonl` (created on first use). Leitner boxes 1-5 with gaps of 1, 3, 7, 14 and 30 days; a wrong answer sends the item back to box 1. `quiz_store.py` handles storage (`due`, `add`, `grade`, `stats`).

## Notes

- Wiki questions are built only from notes Claude actually read, and cite the source note.
- Secrets and personal data are kept out of questions and the store.

MIT License.
