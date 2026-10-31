# 독립 리뷰: `claude/task-0ft2qm` (quiz_store 안정성) vs `main` — 2026-10-31

대상: `origin/claude/task-0ft2qm` (4269c38, 52d7f9a) · 기준: `origin/main` (e15af01)
이 문서의 줄 번호는 **브랜치의** `quiz_store.py` 기준입니다(`git show origin/claude/task-0ft2qm:quiz_store.py`).
프로덕션 코드는 수정하지 않았습니다. 재현 테스트: `review/test_review_repro.py`(임시 HOME, 실제 CLI subprocess, 합성 데이터만 사용).

## 요약
- 브랜치 테스트: **16 tests, 16 pass** (Linux, Python 3.13.18).
- 같은 테스트를 main의 `quiz_store.py`에 돌리면 **failures=48, errors=1** → 테스트가 실제로 회귀를 구분함(핸드오프 문서의 "41건"은 subTest 추가 전 수치로 보임).
- 테스트는 실제 CLI를 subprocess로 실행하고, 실패 주입도 `runpy`로 실제 스크립트를 돌림 → 구현을 그대로 베낀 테스트가 아님.
- 원자적 쓰기·잠금·손상 저장소 거부·인자 검증은 의도대로 동작. **확인된 결함 1건(P2, 심볼릭 링크)**, 나머지는 P3/정적 위험.

## 발견 사항

| # | 분류 | 심각도 | 위치 |
|---|---|---|---|
| F1 | 확인된 결함 | P2 | `quiz_store.py:63`, `:69` |
| F2 | 확인된 결함(동작 변화) | P3 | `quiz_store.py:63` |
| F3 | 확인된 결함 | P3 | `quiz_store.py:152-155`, `:65` |
| F4 | 확인됨(의도된 fail-closed) | P3 | `quiz_store.py:25`, `:55` |
| F5 | 정적 위험 | P3 | `quiz_store.py:95-97` |
| F6 | 정적 위험 | P3 | `quiz_store.py:180` |
| F7 | 정적 위험(미검증) | P3 | `quiz_store.py:77-104`, `:69` (Windows) |

### F1. 심볼릭/하드 링크된 `items.jsonl`이 일반 파일로 바뀜 (P2, 하위 호환 회귀)
- 트리거: `~/.claude/quiz/items.jsonl`이 동기화 폴더 등으로 가는 심볼릭 링크인 상태에서 `add`/`grade`.
- 관찰: `os.replace(tmp, STORE)`가 링크 자체를 교체 → `items.jsonl`은 0600 일반 파일이 되고, 링크 대상 파일은 그대로(0바이트) 남음. 이후 모든 쓰기가 로컬 파일로만 감(동기화 데이터와 조용히 갈라짐). 하드 링크도 링크 수가 1로 끊김. main(`write_text`)은 링크를 따라가 대상에 씀.
- 기대: 링크 대상 파일이 원자적으로 갱신되고 링크 유지.
- 재현: `SymlinkedStore.test_write_goes_through_symlink` — 브랜치 FAIL, main PASS.
- 수정 방향: `save()`에서 `target = Path(os.path.realpath(STORE))`를 구해 그 디렉터리에 `mkstemp`하고 `os.replace(tmp, target)`. (하드 링크는 원자적 교체와 양립 불가 — 문서화로 충분.)

### F2. 저장소 파일 권한이 0644 → 0600으로 바뀜 (P3)
- 트리거: main으로 만든 저장소(0644)에 브랜치로 `add`.
- 관찰: `mkstemp`가 0600으로 만든 파일로 교체되어 권한이 0600이 됨(재현: 수동, 아래 명령 2).
- 기대: 기존 권한 유지(개인 퀴즈 데이터라 0600이 오히려 낫다고 볼 수도 있어 영향은 작음).
- 수정 방향: 교체 전 기존 파일이 있으면 `os.chmod(tmp, stat.S_IMODE(STORE.stat().st_mode))`.

### F3. 홀로 쓰인 서러게이트(`"\ud800"`) 키워드가 traceback으로 끝남 (P3)
- 트리거: `add '{"keyword":"x\ud800"}'` (유효한 JSON 이스케이프지만 UTF-8로 인코딩 불가).
- 관찰(브랜치): `save()` 안에서 `UnicodeEncodeError` traceback, exit 1. 기존 저장소 바이트와 임시파일 정리는 **보존됨**(원자적 쓰기 덕분).
- 참고(main): 같은 입력에서 `write_text`가 먼저 파일을 비운 뒤 실패 → **저장소가 0바이트로 전부 유실**(P1). 브랜치가 이 데이터 유실을 고쳤지만 이 경로를 직접 덮는 테스트는 없음.
- 기대: 사용법 오류(exit 2), 한국어 메시지, traceback 없음.
- 재현: `UnencodableKeyword.test_existing_records_survive`(브랜치 PASS / main FAIL), `test_rejected_as_usage_error`(브랜치 FAIL).
- 수정 방향: `add`의 검증 단계에서 `json.dumps(it, ensure_ascii=False).encode("utf-8")`을 시도하고 `UnicodeEncodeError`면 `usage(...)`. 더 넓게는 `__main__`에서 `OSError`도 잡아 같은 형식으로 안내(디스크 가득 참 등도 지금은 traceback).

### F4. main이 허용하던 레코드가 있으면 저장소 전체가 잠김 (P3, 의도된 동작)
- 트리거: main으로 `add '{"keyword":""}'` 또는 `add '{"keyword":3}'`를 실행해 저장된 저장소를 브랜치로 사용.
- 관찰: `stats`/`due`/`add`/`grade` 모두 `2번째 줄: 'keyword'가 비어 있거나…` 로 exit 1, 파일 무수정.
- 기대: 핸드오프 문서가 밝힌 fail-closed 정책과 일치하며 줄 번호도 알려줌 → 결함으로 보지 않음. 다만 정상 레코드까지 복습이 전부 막히므로, 스킬 사용자(Claude)가 따라 할 복구 안내가 SKILL.md에 없음.
- 재현: `LegacyStore.test_legacy_empty_keyword_record_is_reported_with_line`(브랜치 PASS). 정상적인 main 저장소는 그대로 동작함: `test_normal_legacy_store_round_trips` PASS.
- 수정 방향(선택): 잘못된 레코드는 경고 후 건너뛰고 쓰기 시 보존하거나, SKILL.md에 "오류 줄을 고치거나 삭제" 한 줄 추가.

### F5. 잠금 루프가 모든 `OSError`를 "다른 프로세스가 잡고 있음"으로 취급 (P3, 정적)
- 트리거: `flock`이 `ENOLCK`(일부 NFS)·`EBADF` 등 경쟁과 무관한 이유로 실패.
- 관찰(코드): `except OSError`에서 30초 재시도 후 "다른 quiz_store.py 프로세스가 멈췄는지 확인" 메시지 → 원인을 잘못 안내. 데이터 손상은 없음.
- 수정 방향: `errno`가 `EAGAIN/EWOULDBLOCK/EACCES`(Windows `EDEADLOCK` 포함)일 때만 재시도, 나머지는 즉시 StoreError로 원인 표시.

### F6. exit code를 메시지 부분 문자열로 판정 (P3, 정적)
- `sys.exit(2 if "사용법" in str(e) else 1)`: 저장소 경로(HOME)에 "사용법"이 들어 있으면 손상 저장소 오류도 exit 2. 실사용 영향은 거의 없음.
- 수정 방향: `class UsageError(StoreError)`로 구분.

### F7. Windows 경로 미검증 (P3, 정적)
- `msvcrt.locking` 경로, 그리고 `due`/`stats`가 잠금 없이 파일을 읽는 순간 `os.replace`가 `PermissionError`를 낼 수 있는 점은 Linux에서 확인 불가(핸드오프 문서도 미검증이라 밝힘). 실패 시 임시파일 정리·원본 보존은 코드상 보장되지만 메시지는 traceback.
- 수정 방향: Windows CI 또는 수동 1회 실행; `os.replace`의 `PermissionError`에 짧은 재시도.

## 이미 다뤄진 것 / 문제 없음
- 원자적 쓰기: `os.replace`·`os.fsync` 실패 주입 시 원본 바이트 보존 + 임시파일 없음 — 기존 테스트로 확인.
- 동시성: 기존 테스트(동시 add 16, 중복 add 8, grade 12) 통과. 추가 수동 확인: grade 60개 동시 실행 중 잠금 없는 `stats` 60회 → **읽기 실패 0**, 키워드별 wrong 수 정확(3씩).
- 손상 저장소: 8개 케이스 × 4개 명령에서 바이트 보존·줄 번호 안내 — 기존 테스트로 확인.
- BOM이 붙은 저장소: `utf-8-sig`로 정상 읽힘(수동 확인, 테스트는 없음).
- 하위 호환: main이 정상 `add`/`grade`로 만든 저장소는 브랜치에서 그대로 due/grade/add/stats 가능(재현 테스트로 확인). CRLF·빈 줄 허용 유지.
- `add` 검증은 공백만 있는 keyword를 거부하지만 로더는 허용 — 기존 데이터를 막지 않는 쪽이라 문제 아님.
- 강제 종료(SIGKILL) 시 `items.jsonl.*.tmp`가 남을 수 있으나 원본은 안전하고 로더가 읽지 않음 — 비문제(정리는 선택).
- 브랜치는 `date.fromisoformat` 때문에 Python 3.7+ 필요(main은 3.5+). README는 "Python 3"만 명시 — 참고 수준.

## 테스트 공백(브랜치 테스트에 추가하면 좋은 것)
심볼릭 링크 저장소(F1), 인코딩 불가 입력 시 원본 보존(F3, main의 실제 데이터 유실 경로), main이 만든 저장소 업그레이드(F4), BOM 저장소.

## 사용한 명령
```sh
git fetch origin claude/task-0ft2qm
git diff --stat origin/main...origin/claude/task-0ft2qm
S=<scratch>; git worktree add $S/br origin/claude/task-0ft2qm
(cd $S/br && python3 -m unittest discover -s tests)            # Ran 16, OK
mkdir -p $S/mainrun/tests && cp quiz_store.py $S/mainrun/ && cp $S/br/tests/test_quiz_store.py $S/mainrun/tests/
(cd $S/mainrun && python3 -m unittest discover -s tests)       # failures=48, errors=1

# 재현 테스트 (이 브랜치 루트에서)
git show origin/claude/task-0ft2qm:quiz_store.py > $S/branch_quiz_store.py
QUIZ_STORE_SCRIPT=$S/branch_quiz_store.py LEGACY_QUIZ_STORE_SCRIPT=quiz_store.py \
  python3 -m unittest review/test_review_repro.py -v           # 5 tests, 2 FAIL (F1, F3)
python3 -m unittest review/test_review_repro.py -v             # main 대상: 3 FAIL (main의 서러게이트 데이터 유실 포함)

# 수동 확인 (임시 HOME)
H=$(mktemp -d); HOME=$H python3 quiz_store.py add '{"keyword":"a"}'; stat -c %a $H/.claude/quiz/items.jsonl   # 644 (main)
HOME=$H python3 $S/branch_quiz_store.py add '{"keyword":"b"}'; stat -c %a $H/.claude/quiz/items.jsonl          # 600 (브랜치, F2)
```
