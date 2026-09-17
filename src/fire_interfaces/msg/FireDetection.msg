std_msgs/Header header          # frame_id: 센서 프레임 또는 base_link
string source                   # "vision" | "thermal" | "gas"
bool detected
float32 confidence              # 0.0 ~ 1.0 (정규화 점수)
float32 raw_value               # vision: 모델 점수, thermal: 최고온도[K], gas: 농도[ppm]
float32 bearing                 # base_link 기준 방위[rad], 모르면 NaN
float32 range                   # [m], 모르면 NaN
geometry_msgs/Point position    # map 좌표 추정치
bool position_valid
int32[4] bbox                   # 이미지 좌표 x1,y1,x2,y2 (없으면 -1)
