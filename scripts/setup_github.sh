#!/usr/bin/env bash
# GitHub 저장소 생성 + 첫 푸시 (sudo 불필요, gh 로그인 필요)
# 사용: bash scripts/setup_github.sh [저장소이름] [private|public]
set -eo pipefail
cd "$(dirname "$0")/.."
REPO_NAME="${1:-fire-patrol-sim}"
VISIBILITY="${2:-private}"

command -v gh >/dev/null || { echo "❌ gh 없음 → bash scripts/install_deps.sh"; exit 1; }
gh auth status >/dev/null 2>&1 || { echo "❌ GitHub 로그인 필요 → 터미널에서: gh auth login"; exit 1; }
[[ -n "$(git config --global user.name)" && -n "$(git config --global user.email)" ]] \
  || { echo "❌ git user.name / user.email 설정 필요"; exit 1; }

gh auth setup-git   # git push 가 gh 인증을 쓰도록

[[ -d .git ]] || git init -b main
git add -A
git diff --cached --quiet || git commit -m "chore: 초기 키트 (시나리오/단계 문서/설치 스크립트)"
git branch -M main
git tag -l setup-done | grep -q . || git tag -a setup-done -m "개발 환경 준비 완료"

GH_USER=$(gh api user --jq .login)
if git remote get-url origin >/dev/null 2>&1; then
  echo "== origin 이미 있음: $(git remote get-url origin)"
elif gh repo view "$GH_USER/$REPO_NAME" >/dev/null 2>&1; then
  echo "== 기존 저장소 연결: $GH_USER/$REPO_NAME"
  git remote add origin "https://github.com/$GH_USER/$REPO_NAME.git"
else
  echo "== 새 저장소 생성: $GH_USER/$REPO_NAME ($VISIBILITY)"
  gh repo create "$REPO_NAME" --"$VISIBILITY" --source=. --remote=origin \
    --description "산업현장 자율주행 화재 탐지 로봇 시뮬레이션 (ROS 2 Humble + Gazebo Harmonic)"
fi

git config push.followTags true
git push -u origin main
git push origin --tags
echo "✅ 완료: https://github.com/$GH_USER/$REPO_NAME"
