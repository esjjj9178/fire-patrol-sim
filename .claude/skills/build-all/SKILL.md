---
name: build-all
description: 설치 확인 후 STEP1~STEP7 을 멈추지 않고 한 번에 구현한다. 중단됐으면 미구현 단계부터 이어서 한다.
disable-model-invocation: true
---

`CLAUDE.md` 의 "0. 작업 방식" 페이즈 A → B 를 그대로 수행한다. 추가 지시: $ARGUMENTS

1. `CLAUDE.md`, `PROGRESS.md`, `docs/ARCHITECTURE.md` 를 읽는다.
2. 페이즈 A: `bash scripts/check_deps.sh` 로 점검한다. 누락이 있으면 사용자에게 `bash scripts/install_deps.sh` 실행 요청 후 멈춘다. 원격(origin)이 없으면 `/setup` 을 권한다.
3. 페이즈 B: `PROGRESS.md` 에서 구현이 ✅ 가 아닌 첫 단계부터 STEP7 까지 순서대로 구현한다.
   각 단계마다 빌드 성공 → 정적 검증 → 검증 시트 작성 → PROGRESS 갱신 → 커밋/태그 → push.
   단계 사이에 멈추거나 사용자 확인을 기다리지 않는다.
4. 시작할 때 구현 계획을 단계별 한 줄씩 보여주고 바로 진행한다.
5. 끝나면 요약 표와 위험 요소를 보고하고, `/check 1` 로 검증을 시작하라고 안내한다.
