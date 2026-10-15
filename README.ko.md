# duo-claude

[English](README.md) | **한국어** | [日本語](README.ja.md) | [中文](README.zh-CN.md)

Claude Code용 듀오링고식 복습 스킬입니다. Claude가 작업 한 덩어리를 끝내면 그 작업의 키워드로 4지선다 문제를 내고, 틀린 문제는 간격 반복 일정에 맞춰 다시 냅니다. 문제는 한국어로 나옵니다.

## 설치

```sh
git clone https://github.com/Bum-Boo/duo-claude ~/.claude/skills/duo-claude
```

Python 3이 필요합니다(표준 라이브러리만 사용). 스킬이 적용되도록 Claude Code를 다시 시작하세요.

## 사용법

| 명령 | 동작 |
| --- | --- |
| `/duo-claude` | 켜기. 지금까지의 작업으로 바로 한 번 내고, 이후 작업 한 덩어리가 끝날 때마다 1~2문항을 냅니다. |
| `/duo-claude off` | 이 세션에서 끄기. |
| `/duo-claude wiki [keyword]` | 코드 대신 내 위키·노트에서 출제. 노트 검색/읽기 도구(위키 MCP 등)나 지정한 노트 폴더가 필요합니다. |
| `/duo-claude review` | 복습할 시기가 된 문제만. |
| `/duo-claude stats` | 누적 문항, 복습 대기, 자주 틀린 키워드. |

작업 도중에는 끼어들지 않고 사소한 수정은 건너뜁니다. 켜짐/꺼짐 상태는 대화 안에만 있으므로 새 세션에서는 `/duo-claude`를 다시 입력하세요.

## 복습 방식

문제는 `~/.claude/quiz/items.jsonl`에 저장됩니다(처음 쓸 때 생성). 라이트너 상자 1~5, 간격 1·3·7·14·30일이며 틀리면 상자 1로 돌아갑니다. 저장은 `quiz_store.py`(`due`, `add`, `grade`, `stats`)가 맡습니다.

## 참고

- 위키 문제는 Claude가 실제로 읽은 노트에서만 만들고 근거 노트를 함께 알려줍니다.
- 비밀값과 개인정보는 문제와 저장소에 넣지 않습니다.

MIT 라이선스.
