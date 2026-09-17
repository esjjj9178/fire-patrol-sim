# STEP5 — 열화상 노드 · 가스 가상센서 노드

> **작업 방식 메모**: 구현(`/build-all`) 때는 빌드·정적 검증까지만 한다. 아래의 시뮬 실행 검증·데이터 수집·학습은 검증(`/check`) 때 수행하며, 그 절차를 `docs/verify/` 검증 시트에 옮겨 적는다. "완료 기준"은 검증 시트의 체크리스트가 된다.

## 목표
`/fire/thermal/detection`, `/fire/gas/detection` 이 발행되고, real/fake/hidden 불에 대해 기대대로 반응한다.

## 할 일
1. **열화상 원시값 해석 확정**
   - Gazebo thermal 카메라 출력 인코딩과 해상도(K 단위 스케일)를 설치 버전 기준으로 확인하고 `perception.yaml` 에 기록
   - 확인 방법: real_fire 를 정면에 두고 픽셀 최대값 로그 → 600K 와 대응 확인
2. `thermal_node.py`
   - `/thermal/image_raw` → 켈빈 변환 → `/thermal/temperature_image`(32FC1)
   - 최고온도 Tmax, 핫스팟 픽셀 → bearing(열화상 HFOV + 팬 각도)
   - 점수 = ARCHITECTURE.md 의 변환식, detected = 점수 ≥ 0.5
   - range 는 NaN (옵션: 같은 방향 depth 값 참조 파라미터)
3. `virtual_thermal_node.py` (**SIM ONLY 폴백**, `virtual_thermal:=true`)
   - Gazebo 열화상이 동작하지 않거나 너무 느릴 때 사용
   - layout yaml(불 위치/온도) + `/ground_truth/pose` + 팬 각도로 32×24 이미지 생성
   - 선반/벽에 대한 **2D 가시선 검사**(가려지면 안 보임), 거리 감쇠, 가우시안 블러, 노이즈
   - 출력 형식은 실제 브리지 토픽과 동일(`/thermal/image_raw`)
4. `gas_sim_node.py` (**SIM ONLY**)
   - layout yaml 의 `is_real: true` 불만 가스 발생
   - 농도: `base_ppm + Σ strength·exp(-d²/(2σ²))`, 기본 base 250, σ 1.5m, 가시선 무관(확산 가정)
   - MQ-2 응답 지연: 1차 지연 τ=2s, 가우시안 노이즈, 10Hz
   - `/gas/concentration`, `/fire/gas/detection`(bearing/range NaN) 발행
   - 옵션: 최근 이동 중 농도 변화로 **대략적 방향 힌트**(gradient) 계산해 bearing에 넣기(파라미터, 기본 off)
5. perception.launch.py 에 thermal / virtual_thermal / gas 추가
6. 시나리오 단위 테스트 스크립트 `fire_perception/tools/sensor_scenario_test.py`
   - 로봇을 각 불 근처 지정 위치로 순간이동(Gazebo set_pose 서비스, SIM ONLY) → 팬을 불 방향으로 → 3초간 세 센서 점수 평균 기록
   - 결과 표: 위치 × (vision, thermal, gas)

## 기대 결과 표 (검증 기준)
| 위치 | vision | thermal | gas |
|---|---|---|---|
| real_fire 앞 2m | 높음 | 높음 | 높음 |
| fake_fire 앞 2m | 높음 | 낮음 | 낮음 |
| hidden_fire 모퉁이 전(안 보임) | 낮음 | 낮음 | 중간~높음 |
| 불 없는 곳 | 낮음 | 낮음 | 낮음 |

## 완료 기준
- [ ] 열화상 스케일 확정, real_fire Tmax ≈ 600K(±30)
- [ ] 위 기대 결과 표와 실제 측정 표 비교 보고
- [ ] virtual_thermal 모드도 같은 표 통과
- [ ] 가스 농도 그래프(거리별) 출력 이미지 저장 `data/plots/gas_vs_distance.png`
