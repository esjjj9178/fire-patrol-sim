---
name: pass
description: 지정한 단계(예 /pass 3)를 검증 완료로 기록한다.
disable-model-invocation: true
argument-hint: <단계 번호>
---

단계: $ARGUMENTS

1. `PROGRESS.md` 에서 해당 단계 "검증"을 ✅ 로 바꾸고, 사용자가 미확인으로 남긴 항목이 있으면 메모에 ⚠️ 로 적는다.
2. `git add -A && git commit -m "stepN: 검증 완료"` → 태그 `stepN-verified` 생성(이미 있으면 CLAUDE.md Git 규칙대로 삭제 후 재생성, 강제 푸시 금지) → `git push origin main --follow-tags`
3. 다음으로 검증할 단계를 알려주고(`/check N+1`) 멈춘다. 모든 단계가 ✅ 면 `git tag -a v0.1-sim -m "시뮬 v0.1"` 을 만들어 push 하고 완료를 알린다.
