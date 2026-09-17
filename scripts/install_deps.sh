#!/usr/bin/env bash
# 누락된 것만 설치한다. sudo 없이 실행할 것: bash scripts/install_deps.sh
# (내부에서 필요한 부분만 sudo 를 사용. pip 는 사용자 계정(--user)으로 설치)
set -eo pipefail
if [[ $EUID -eq 0 ]]; then
  echo "❌ 'sudo bash' 로 실행하지 마세요. 그냥 'bash scripts/install_deps.sh' 로 실행하세요."; exit 1
fi
cd "$(dirname "$0")/.."
source scripts/deps_list.sh

echo "== sudo 권한 확인 (비밀번호 1회 입력) =="
sudo -v

need_update=0

# --- ROS 2 apt 저장소 ---
missing_ros=()
for p in "${ROS_APT[@]}"; do is_apt_installed "$p" || missing_ros+=("$p"); done
if (( ${#missing_ros[@]} )) && ! ros_repo_configured; then
  echo "== ROS 2 저장소 등록 =="
  sudo apt-get update
  sudo apt-get install -y software-properties-common curl locales
  sudo locale-gen en_US en_US.UTF-8 >/dev/null
  sudo add-apt-repository -y universe
  ROS_APT_SOURCE_VERSION=$(curl -s https://api.github.com/repos/ros-infrastructure/ros-apt-source/releases/latest | grep -F '"tag_name"' | awk -F'"' '{print $4}')
  CODENAME=$(. /etc/os-release && echo "$VERSION_CODENAME")
  curl -L -o /tmp/ros2-apt-source.deb \
    "https://github.com/ros-infrastructure/ros-apt-source/releases/download/${ROS_APT_SOURCE_VERSION}/ros2-apt-source_${ROS_APT_SOURCE_VERSION}.${CODENAME}_all.deb"
  sudo dpkg -i /tmp/ros2-apt-source.deb
  need_update=1
fi

# --- Gazebo(OSRF) 저장소 ---
if ! gz_harmonic_ok && ! osrf_repo_configured; then
  echo "== Gazebo(OSRF) 저장소 등록 =="
  sudo curl -fsSL https://packages.osrfoundation.org/gazebo.gpg -o /usr/share/keyrings/pkgs-osrf-archive-keyring.gpg
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/pkgs-osrf-archive-keyring.gpg] http://packages.osrfoundation.org/gazebo/ubuntu-stable $(. /etc/os-release && echo "$VERSION_CODENAME") main" \
    | sudo tee /etc/apt/sources.list.d/gazebo-stable.list > /dev/null
  need_update=1
fi

# --- GitHub CLI 저장소 ---
if ! is_apt_installed gh && ! gh_repo_configured; then
  echo "== GitHub CLI 저장소 등록 =="
  sudo mkdir -p -m 755 /etc/apt/keyrings
  tmp=$(mktemp)
  wget -nv -O "$tmp" https://cli.github.com/packages/githubcli-archive-keyring.gpg
  sudo tee /etc/apt/keyrings/githubcli-archive-keyring.gpg < "$tmp" > /dev/null
  sudo chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
    | sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null
  need_update=1
fi

# --- apt 누락분 설치 (충돌 패키지 자동 제외, 실패해도 나머지는 계속) ---
to_install=()
for p in "${ROS_APT[@]}" "${SYS_APT[@]}"; do
  # Harmonic 연동이 이미 있으면 Fortress용 ros-humble-ros-gz* 는 설치하지 않음
  if [[ "$p" == ros-humble-ros-gz || "$p" == ros-humble-ros-gz-* ]] && is_apt_installed ros-humble-ros-gzharmonic-bridge; then
    echo "  (건너뜀) $p — Harmonic 연동 패키지와 충돌"; continue
  fi
  is_apt_installed "$p" || to_install+=("$p")
done
gz_harmonic_ok || to_install+=(gz-harmonic)

failed=()
if (( ${#to_install[@]} )); then
  echo "== apt 설치 (${#to_install[@]}개): ${to_install[*]}"
  sudo apt-get update
  if ! sudo apt-get install -y "${to_install[@]}"; then
    echo "== 일괄 설치 실패 → 하나씩 설치합니다"
    for p in "${to_install[@]}"; do
      if sudo apt-get install -y "$p" >/tmp/apt_$p.log 2>&1; then
        echo "  ✅ $p"
      else
        echo "  ❌ $p (로그: /tmp/apt_$p.log)"; failed+=("$p")
      fi
    done
  fi
else
  echo "== apt: 모두 설치되어 있음 (건너뜀)"
  (( need_update )) && sudo apt-get update
fi

# --- 오래된 버전이라 apt-get install 로는 안 잡히는 패키지(upgrade 필요) ---
if ! diagnostic_updater_lib_ok; then
  echo "== ros-humble-diagnostic-updater 버전 올림(.so 없는 구버전 → laser_filters/ekf_node 크래시 원인) =="
  sudo apt-get update
  sudo apt-get install --only-upgrade -y ros-humble-diagnostic-updater
  diagnostic_updater_lib_ok || echo "⚠️  upgrade 후에도 libdiagnostic_updater.so 를 못 찾음 - 로그 확인 필요"
fi

# --- rosdep ---
if [[ ! -f /etc/ros/rosdep/sources.list.d/20-default.list ]]; then
  echo "== rosdep init =="
  sudo rosdep init
fi
rosdep update >/dev/null 2>&1 || echo "⚠️  rosdep update 실패(네트워크 확인). 진행은 계속합니다."

# --- pip (사용자 계정) ---
PIP="python3 -m pip install --user"
if ! py_numpy_ok; then echo "== numpy<2 설치"; $PIP "numpy<2"; fi
if ! py_torch_ok; then
  echo "== torch/torchvision (CPU) 설치 — 수 분 걸릴 수 있음"
  $PIP torch torchvision --index-url https://download.pytorch.org/whl/cpu
fi
if ! py_ultralytics_ok; then
  echo "== ultralytics 설치"
  $PIP ultralytics "numpy<2" "opencv-python<4.12"
fi
if ! py_numpy_ok; then echo "== numpy 가 2.x 로 올라가서 되돌림"; $PIP --force-reinstall "numpy<2"; fi
if ! py_cv2_ok; then echo "== cv2 재설치"; $PIP --force-reinstall "opencv-python<4.12" "numpy<2"; fi

echo
echo "== 설치 후 점검 =="
bash scripts/check_deps.sh || true
if (( ${#failed[@]} )); then
  echo
  echo "⚠️  설치 실패한 apt 패키지: ${failed[*]}"
  echo "    각 /tmp/apt_<패키지>.log 마지막 부분을 Claude 에게 붙여넣어 주세요."
fi
echo
echo "다음 할 일:"
echo "  1) GitHub 로그인이 안 되어 있으면:  gh auth login   (GitHub.com → HTTPS → 브라우저 로그인)"
echo "  2) Claude Code 로 돌아가서 '설치 끝났어' 라고 입력"
