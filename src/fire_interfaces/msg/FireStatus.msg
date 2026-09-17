std_msgs/Header header
string fire_state               # NONE | SUSPECT | VERIFY | CONFIRMED | FALSE_ALARM
string mission_state             # PATROL | SEARCH | VERIFY | APPROACH | HOLD
float32 fused_score
float32 vision_score
float32 thermal_score
float32 gas_score
geometry_msgs/Point fire_position   # map
bool position_valid
string reason                    # 사람이 읽는 판단 근거
