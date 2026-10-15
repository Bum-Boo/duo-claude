# duo-claude

[English](README) | [한국어](README.ko) | [日本語](README.ja) | **中文**

面向 Claude Code 的多邻国式复习技能。Claude 每完成一段工作,就用该工作的关键词出四选一题目,答错的题会按间隔重复计划再次出现。题目使用韩语。

## 安装

```sh
git clone https://github.com/Bum-Boo/duo-claude ~/.claude/skills/duo-claude
```

需要 Python 3(仅用标准库)。请重启 Claude Code 以加载该技能。

## 用法

| 命令 | 作用 |
| --- | --- |
| `/duo-claude` | 开启。立即根据当前会话的工作出题,之后每完成一段工作出 1~2 题。 |
| `/duo-claude off` | 在本会话中关闭。 |
| `/duo-claude wiki [keyword]` | 从你自己的维基/笔记出题,而不是代码。需要笔记搜索/读取工具(如维基 MCP)或你指定的笔记文件夹。 |
| `/duo-claude review` | 只出到了复习时间的题。 |
| `/duo-claude stats` | 总数、待复习数、最常答错的关键词。 |

不会在工作途中打断,琐碎的修改也会跳过。开/关状态只存在于对话中,新会话需要重新运行 `/duo-claude`。

## 复习方式

题目保存在 `~/.claude/quiz/items.jsonl`(首次使用时创建)。采用莱特纳盒子 1~5,间隔为 1、3、7、14、30 天,答错则回到盒子 1。存储由 `quiz_store.py`(`due`、`add`、`grade`、`stats`)负责。

## 说明

- 维基题目只来自 Claude 实际读过的笔记,并注明来源笔记。
- 密钥和个人信息不会写入题目或存储。

MIT 许可证。
