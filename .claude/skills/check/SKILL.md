---
name: check
description: 지정한 단계(예 /check 3)의 검증을 시작한다. 사용자 실행 명령 안내와 Claude가 가능한 자동 확인을 함께 한다.
disable-model-invocation: true
argument-hint: <단계 번호>
---

검증할 단계: $ARGUMENTS (비어 있으면 PROGRESS.md 에서 검증이 ✅ 가 아닌 첫 단계)

1. `PROGRESS.md` 와 `docs/verify/STEP{N}_VERIFY.md`, `docs/steps/STEP{N}.md` 를 읽는다.
2. 해당 단계 구현이 ✅ 가 아니면 알리고 멈춘다. 앞 단계가 검증 전이면 의존 관계를 한 줄로 알린다.
3. 빌드가 최신인지 확인(`colcon build --symlink-install`).
4. Claude가 GUI 없이 확인 가능한 항목은 timeout 을 걸어 직접 실행하고 결과를 표로 보고한 뒤 프로세스를 정리한다.
5. 사용자가 눈으로 봐야 하는 항목은 검증 시트의 명령을 **터미널별 코드블록**으로 보여주고, 무엇을 보면 되는지 짧게 적는다.
6. 체크리스트를 현재까지 결과로 채워서 보여주고, 사용자에게 결과(또는 에러 로그)를 알려달라고 한다.
7. 문제가 있으면 원인을 좁혀 수정 → 재빌드 → 다시 확인할 명령 안내. 모두 통과하면 `/pass N` 을 안내한다.
