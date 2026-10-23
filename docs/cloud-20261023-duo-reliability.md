# duo-claude quiz_store.py 안정성 개선 핸드오프 (2026-10-23)

브랜치: `claude/task-0ft2qm` · 변경: `quiz_store.py`, `tests/test_quiz_store.py`, 본 문서

## 실행 명령과 결과
```
python3 -m unittest discover -s tests -v     # 16 tests, 16 pass, 0 fail (Linux, Python 3.13, ~4s; 리뷰 반영 후 재실행)
```
회귀 검증: 변경 전 `quiz_store.py`(HEAD)로 같은 테스트를 돌리면 **41건 실패**(subTest 포함; 동시 add/grade에서 레코드 유실 재현, 손상 파일 처리·인자 검증 부재 확인). 변경 후 전부 통과.
모든 테스트는 임시 HOME/USERPROFILE로 실제 CLI(`python -X utf8 quiz_store.py`)를 subprocess로 실행합니다. 실제 홈의 퀴즈 데이터는 건드리지 않습니다.

## 변경 내용
1. **원자적 저장**: 같은 디렉터리에 임시파일 작성 → flush+fsync → `os.replace`. 실패 시 임시파일 삭제, 기존 파일 바이트 보존.
2. **동시성**: `items.jsonl.lock` 파일에 대한 프로세스 간 잠금(POSIX `fcntl.flock`, Windows `msvcrt.locking`)으로 add/grade의 read-modify-write 전체를 감쌈. 30초 대기 후 실패 시 안내 메시지. (stdlib만 사용; 읽기 명령 due/stats는 원자적 교체 덕분에 잠금 불필요.)
3. **손상 저장소**: 모든 명령이 로드 시 레코드를 검증(JSON 객체, keyword 문자열, box 1~5, seen/wrong 0 이상 정수, next 정규 `YYYY-MM-DD` 형식 날짜(due/stats가 문자열 비교를 하므로 `20260101`·`2026-1-1` 같은 형식은 `isoformat()` 왕복 검사로 거부), UTF-8). 문제 시 줄 번호가 있는 한국어 오류 + exit 1, 파일은 **쓰지 않음**(바이트 동일 테스트).
4. **인자 검증**(저장소 미수정, exit 2 + 사용법): add는 비어 있지 않은 문자열 `keyword`를 가진 JSON 객체 1개 필요; grade는 정확히 `<keyword> right|wrong`(이전에는 `right` 외 아무 값이나 오답 처리); due는 인자 최대 1개(n, 0 이상 정수), stats는 인자 없음(초과 인자는 exit 2); 알 수 없는 명령 거부.
5. `main()`은 `if __name__ == "__main__"` 안에서만 실행(CLI 동작 동일).

## 유지된 동작
스키마(keyword/question/…/box/next/seen/wrong/added), Leitner 간격 1/3/7/14/30일, 중복 keyword add는 조용히 무시, `ensure_ascii=False`(한글 그대로 저장), due 기본 4개·정렬. `grade`로 없는 keyword를 주면 여전히 exit 0이지만 이제 stderr 경고를 내고 파일을 다시 쓰지 않음.

## 이미 올바르게 처리되던 것
빈 줄 무시, CRLF 줄바꿈 읽기, UTF-8 한글 입출력은 기존에도 정상이라 변경 없음(테스트로 고정).

## 미검증 / 남은 문제
- **Windows 미검증**: `msvcrt.locking` 경로와 `os.replace`(다른 프로세스가 대상 파일을 열고 있으면 PermissionError 가능)는 이 환경(Linux)에서 실행해 보지 못했습니다. 코드상 비차단 잠금+재시도 루프이며, 실패 시 오류로 끝나고 데이터는 보존됩니다. Windows에서 `python -m unittest discover -s tests`를 한 번 돌려 확인 필요.
- NFS 등 일부 네트워크 파일시스템에서는 flock 보장이 약할 수 있음.
- 정전 시 디렉터리 fsync는 하지 않음(파일 fsync + 원자적 replace까지).
- 이전에 부분적으로 깨진 기존 저장소가 있으면 이제 명령이 오류로 멈춤(의도된 동작; 오류 메시지의 줄을 수동 수정해야 함).
- 실패 쓰기 테스트는 `os.replace`/`os.fsync`를 주입 실패시키는 방식이며 실제 프로세스 강제종료는 아님.

## 리뷰 반영 (Codex)
- 커밋된 `tests/__pycache__/*.pyc` 제거, `.gitignore`(`__pycache__/`, `*.pyc`) 추가.
- due/stats 인자 개수 엄격 검증 + 저장소 바이트 보존 CLI 테스트 추가(`due 1 extra`, `stats extra`).
- `next` 필드는 정규 ISO 왕복 검사; 기본 형식/비패딩 날짜 손상 케이스 테스트 추가. 한계: 기존 저장소에 비정규 날짜가 있었다면 이제 오류로 멈춤(이전에는 잘못된 정렬/due 판정을 조용히 일으킴).
- 재실행 결과: 16 tests, 16 pass (Linux). 테스트 개수는 그대로이고 subTest 케이스만 늘었습니다. Windows는 여전히 미검증.
