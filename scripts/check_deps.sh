#!/usr/bin/env bash
# 설치 상태 점검 (sudo 불필요). 누락 목록을 scripts/.deps_missing 에 기록.
# 종료코드: 0 = 필수 항목 모두 설치됨, 1 = 누락 있음
cd "$(dirname "$0")/.."
source scripts/deps_list.sh

MISSING_FILE="scripts/.deps_missing"
: > "$MISSING_FILE"
missing=0

printf "\n== 시스템 ==\n"
. /etc/os-release
printf "  OS: %s\n" "$PRETTY_NAME"
[[ "$VERSION_ID" != "22.04" ]] && printf "  ⚠️  Ubuntu 22.04 가 아닙니다 (Humble 권장 환경 아님)\n"
if command -v glxinfo >/dev/null; then
  printf "  렌더러: %s\n" "$(glxinfo -B 2>/dev/null | grep -m1 'OpenGL renderer' | cut -d: -f2- | xargs)"
fi

printf "\n== apt 패키지 ==\n"
for p in "${ROS_APT[@]}" "${SYS_APT[@]}"; do
  if is_apt_installed "$p"; then
    printf "  ✅ %s\n" "$p"
  else
    printf "  ❌ %s\n" "$p"; echo "apt $p" >> "$MISSING_FILE"; missing=1
  fi
done

printf "\n== Gazebo ==\n"
if gz_harmonic_ok; then printf "  ✅ Gazebo Harmonic (gz sim %s)\n" "$(gz sim --versions 2>/dev/null | head -1)"
else printf "  ❌ Gazebo Harmonic (gz sim 8.x) 없음\n"; echo "apt gz-harmonic" >> "$MISSING_FILE"; missing=1; fi
if is_apt_installed ros-humble-ros-gz-bridge && ! is_apt_installed ros-humble-ros-gzharmonic-bridge; then
  printf "  ⚠️  Fortress용 ros-humble-ros-gz 가 설치되어 있음 (이 프로젝트는 Harmonic 사용)\n"
fi

printf "\n== 런타임 라이브러리 ==\n"
if diagnostic_updater_lib_ok; then printf "  ✅ libdiagnostic_updater.so (laser_filters/robot_localization 런타임 의존)\n"
else
  printf "  ❌ libdiagnostic_updater.so 없음 → ros-humble-diagnostic-updater 버전이 오래됨(4.0.6, .so 없음).\n"
  printf "      scan_to_scan_filter_chain/ekf_node 가 즉시 죽는다 → apt upgrade 필요.\n"
  echo "apt-upgrade ros-humble-diagnostic-updater" >> "$MISSING_FILE"; missing=1
fi

printf "\n== Python (pip --user) ==\n"
if py_numpy_ok; then printf "  ✅ numpy<2 (%s)\n" "$(python3 -c 'import numpy;print(numpy.__version__)')"
else printf "  ❌ numpy<2 필요\n"; echo "pip numpy" >> "$MISSING_FILE"; missing=1; fi
if py_torch_ok; then printf "  ✅ torch (%s)\n" "$(python3 -c 'import torch;print(torch.__version__)')"
else printf "  ❌ torch (CPU)\n"; echo "pip torch" >> "$MISSING_FILE"; missing=1; fi
if py_ultralytics_ok; then printf "  ✅ ultralytics\n"
else printf "  ❌ ultralytics\n"; echo "pip ultralytics" >> "$MISSING_FILE"; missing=1; fi
if py_cv2_ok; then printf "  ✅ cv2 + numpy import\n"
else printf "  ❌ cv2 import 실패\n"; echo "pip cv2" >> "$MISSING_FILE"; missing=1; fi

printf "\n== 기타 ==\n"
if [[ -f /etc/ros/rosdep/sources.list.d/20-default.list ]]; then printf "  ✅ rosdep init\n"
else printf "  ❌ rosdep init\n"; echo "rosdep init" >> "$MISSING_FILE"; missing=1; fi
if command -v gh >/dev/null && gh auth status >/dev/null 2>&1; then printf "  ✅ GitHub 로그인(gh)\n"
else printf "  ⬜ GitHub 로그인 안 됨 → 터미널에서: gh auth login\n"; fi
if [[ -n "$(git config --global user.name)" && -n "$(git config --global user.email)" ]]; then
  printf "  ✅ git 사용자: %s <%s>\n" "$(git config --global user.name)" "$(git config --global user.email)"
else printf "  ⬜ git user.name / user.email 미설정\n"; fi

printf "\n"
if [[ $missing -eq 0 ]]; then
  echo "결과: 필수 패키지 모두 설치됨"
else
  echo "결과: 누락 $(wc -l < "$MISSING_FILE")개 → 다른 터미널에서 실행: bash ~/fire_ws/scripts/install_deps.sh"
fi
exit $missing
