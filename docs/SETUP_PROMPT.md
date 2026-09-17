# SETUP 프롬프트 — 개발 환경 준비 + GitHub 저장소 연결 → 전체 구현 시작

> `/setup` 으로 실행된다. 슬래시 명령이 안 보이면 이 파일 내용을 Claude Code 에 그대로 붙여넣어도 된다.
> 전제: `~/fire_ws` 에서 `claude` 를 실행한 상태.

너는 이 프로젝트의 개발 환경을 준비한다. 먼저 `CLAUDE.md` 를 읽어라. 아래 순서를 지키고, 각 단계 결과를 한두 줄로 보고하라.

## 1. 질문 (한 번에 모아서 1회만)
아래를 한 메시지로 묻고, 사용자가 "기본값"이라고 하면 기본값을 쓴다.
- GitHub 저장소 이름 (기본: `fire-patrol-sim`)
- 공개 범위 (기본: `private`)
- git 사용자 이름/이메일 — `git config --global user.name/user.email` 이 **비어 있을 때만** 묻는다

## 2. 설치 상태 점검 (설치된 건 건너뜀)
1. `bash scripts/check_deps.sh` 실행 → 결과 표를 요약해서 보여준다.
2. 누락이 있으면:
   - 누락 목록을 보여주고, 사용자에게 **다른 터미널에서** 아래 실행을 요청한 뒤 멈춘다.
     ```
     cd ~/fire_ws && bash scripts/install_deps.sh
     ```
     (`sudo bash` 로 실행하지 말 것, 비밀번호는 스크립트가 한 번 묻는다)
   - 사용자가 "끝났어"라고 하면 `check_deps.sh` 를 다시 실행해 확인한다. 실패 항목이 있으면 로그를 받아 원인을 짚고 스크립트를 고친다.
3. 스크립트는 **누락된 것만** 설치하도록 되어 있다. 너는 `sudo` 를 직접 실행하지 않는다.

## 3. git 설정
- 1번에서 받은 값으로 비어 있을 때만 `git config --global user.name "..."`, `git config --global user.email "..."` 실행.
- `git config --global init.defaultBranch main`

## 4. GitHub 로그인 확인
- `gh auth status` 확인. 안 되어 있으면 사용자에게 **다른 터미널에서** 실행을 요청하고 멈춘다.
  ```
  gh auth login
  ```
  선택: `GitHub.com` → `HTTPS` → `Y`(git 인증에 사용) → `Login with a web browser`
- 사용자가 "로그인 했어"라고 하면 다시 확인한다.

## 5. 저장소 생성 + 첫 푸시
- `bash scripts/setup_github.sh <저장소이름> <private|public>` 실행.
- 이미 같은 이름의 저장소가 있으면 스크립트가 연결만 한다. 원격에 다른 내용이 있어 push 가 거절되면 **강제 푸시하지 말고** 사용자에게 상황과 선택지(다른 이름 사용 / 원격 내용 가져와 병합)를 알려라.
- 성공하면 저장소 URL 을 보여준다.

## 6. 자동 푸시 규칙 확인
이후 모든 작업에서 CLAUDE.md 의 "Git 규칙"을 따른다: **커밋·태그를 만들 때마다 바로 push**.
`git remote -v`, `git log --oneline -3`, `git ls-remote --tags origin` 으로 연결 상태를 보고한다.

## 7. PROGRESS.md 갱신
- "SETUP" 행을 ✅ 로, 저장소 URL 을 메모에 적는다. 현재 페이즈를 `B (구현 대기)` 로 바꾼다.
- 커밋 `chore: setup 완료` → push.

## 8. 바로 전체 구현 시작
준비 요약(설치 ✅ / git ✅ / GitHub URL)을 3줄로 보여준 뒤, **이어서 `/build-all` 절차(.claude/skills/build-all/SKILL.md)를 그대로 수행한다.**
(사용자가 "여기까지만"이라고 했으면 멈추고 `/build-all` 을 안내한다.)
