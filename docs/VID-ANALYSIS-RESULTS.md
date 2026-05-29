# 윈도우별 리턴값 — 실측 원본 (M5, 비평 프롬프트)

면접관 비평 프레이밍: 채널①(비언어)·②(평가) 둘 다 변별 강제(0.8 앵커링/호평 보일러플레이트 제거). per-window 리턴값 전체, 해석 없음. 증거: `.sisyphus/evidence/m5-e2e.json`.


## vid_0001.mp4 — 43.5s, 비언어 15 · 평가 3
지연: 비언어 {'n': 15, 'min': 0.51, 'max': 0.71, 'mean': 0.61} · 평가 {'n': 3, 'min': 6.48, 'max': 7.3, 'mean': 7.03} · end-of-turn 확정 7.83s

```json
[0] {"channel": "nonverbal", "t": 1.5, "window_s": 3.0, "state": "neutral", "intensity": 0.3, "note": "시선은 정면을 응시하나, 미세한 눈 깜빡임과 입술 움직임에서 약간의 긴장감이 느껴짐"}
```
```json
[1] {"channel": "nonverbal", "t": 4.5, "window_s": 3.0, "state": "neutral", "intensity": 0.3, "note": "시선은 정면을 응시하나, 미세한 표정 변화나 자세의 긴장감이 관찰되지 않음"}
```
```json
[2] {"channel": "nonverbal", "t": 7.5, "window_s": 3.0, "state": "neutral", "intensity": 0.3, "note": "시선은 정면을 응시하나, 미세한 표정 변화나 자세의 긴장감이 관찰되지 않음"}
```
```json
[3] {"channel": "nonverbal", "t": 10.5, "window_s": 3.0, "state": "neutral", "intensity": 0.3, "note": "시선은 정면을 응시하나, 미세한 표정 변화나 자세의 긴장감이 관찰되지 않음"}
```
```json
[4] {"channel": "nonverbal", "t": 13.5, "window_s": 3.0, "state": "engaged", "intensity": 0.6, "note": "눈 맞춤 유지, 미세한 미소와 함께 적극적인 자세"}
```
```json
[5] {"channel": "evaluation", "window_start_s": 0.0, "window_dur_s": 16.0, "verbal": {"logic": "자기소개에 필요한 기본 정보(이름, 학년, 전공, 학교)를 명확하게 전달하고 있습니다. 하지만 'tech enthusiast'라는 표현이 다소 추상적입니다.", "structure": "전형적인 자기소개 구조를 따르고 있어 이해하기 쉽습니다. 다만, 문장 간의 연결이 다소 딱딱하게 느껴집니다.", "specificity": "전공(CS)과 학교(Manipal University Jaipur)는 구체적이지만, 'tech enthusiast'와 같은 부분은 구체성이 부족합니다."}, "vocal": {"volume": "적절한 볼륨으로 안정적으로 들립니다.", "pace": "전반적으로 일정한 속도를 유지하고 있으나, 일부 구간에서 약간의 속도 조절이 필요해 보입니다.", "pauses": "문장과 문장 사이의 간격이 적절하여 호흡이 자연스럽습니다.", "intonation": "전반적으로 평이한 톤으로 말하고 있어, 열정이나 흥미를 전달하는 데는 다소 부족함이 있습니다."}, "visual": {"eye_contact": "카메라를 응시하려는 노력이 보이나, 시선이 약간 불안정하게 움직이는 경향이 있습니다.", "posture": "상체는 비교적 안정적인 자세를 유지하고 있습니다.", "expression": "표정은 무난하지만, 자신감이나 열정을 드러내기에는 다소 밋밋합니다.", "gesture_over_time": "특별한 제스처는 사용되지 않았습니다."}, "critique": ["자기소개에 'tech enthusiast'라는 표현을 사용했지만, 이 부분이 어떤 의미인지 구체적인 경험이나 관심사로 뒷받침되지 않아 공허하게 들립니다.", "전반적인 톤이 너무 평이하여, 지원자가 가진 기술에 대한 열정이나 흥미를 효과적으로 전달하지 못하고 있습니다.", "시선 처리가 다소 불안정하여, 면접관과의 소통에 있어 확신이 부족해 보입니다."], "key_observations": ["기본적인 정보 전달은 명확하나, 인상적인 어필 포인트가 부족합니다.", "자신감 있는 태도와 열정적인 톤으로 개선이 필요합니다."]}
```
```json
[6] {"channel": "nonverbal", "t": 16.5, "window_s": 3.0, "state": "engaged", "intensity": 0.6, "note": "눈 맞춤 유지, 미세한 미소와 함께 적극적인 경청 태도 보임"}
```
```json
[7] {"channel": "nonverbal", "t": 19.5, "window_s": 3.0, "state": "neutral", "intensity": 0.3, "note": "시선은 정면을 응시하나, 미세한 표정 변화나 자세의 변화는 관찰되지 않음"}
```
```json
[8] {"channel": "nonverbal", "t": 22.5, "window_s": 3.0, "state": "engaged", "intensity": 0.6, "note": "시선은 카메라를 응시하고 있으나, 미세한 입술 떨림과 약간의 긴장감이 보임"}
```
```json
[9] {"channel": "nonverbal", "t": 25.5, "window_s": 3.0, "state": "neutral", "intensity": 0.3, "note": "표정 변화가 거의 없고 시선이 정면을 응시하고 있으나, 미세한 긴장감이 느껴짐"}
```
```json
[10] {"channel": "nonverbal", "t": 28.5, "window_s": 3.0, "state": "neutral", "intensity": 0.3, "note": "시선이 정면을 응시하고 있으나, 표정 변화가 거의 없어 중립적임"}
```
```json
[11] {"channel": "evaluation", "window_start_s": 16.0, "window_dur_s": 16.0, "verbal": {"logic": "AI와 머신러닝에 대한 관심 표명 후, 블록체인과 탈중앙화 앱으로 관심사를 확장하는 흐름은 논리적입니다. 하지만 'exploring the realm of blockchain'과 같은 표현은 다소 추상적입니다.", "structure": "관심 분야를 나열하는 구조는 명확하나, 각 분야에 대한 깊이 있는 설명 없이 나열식으로 끝나는 경향이 있습니다.", "specificity": "AI와 머신러닝은 언급되었으나, 블록체인에 대한 관심이 'playing with softwares'라는 다소 모호한 표현으로 마무리되어 구체성이 떨어집니다."}, "vocal": {"volume": "적절한 볼륨을 유지하고 있으나, 전반적으로 힘이 부족하게 들립니다.", "pace": "말의 속도는 안정적이지만, 특정 단어에서 약간의 망설임이 느껴집니다.", "pauses": "자연스러운 호흡을 위한 쉼표는 있으나, 문장 전환 시의 멈춤이 다소 어색합니다.", "intonation": "전반적으로 단조로운 톤으로, 관심 분야에 대한 열정이나 흥미가 충분히 전달되지 않습니다."}, "visual": {"eye_contact": "카메라를 응시하려는 시도는 보이나, 시선이 불안정하게 흔들리는 경향이 있습니다.", "posture": "상체는 비교적 안정적이나, 어깨가 약간 경직되어 보입니다.", "expression": "표정은 무표정에 가깝고, 관심 분야에 대한 진정성 있는 흥미가 드러나지 않습니다.", "gesture_over_time": "손동작이나 제스처가 거의 없어, 전달하고자 하는 내용에 대한 몰입도가 낮아 보입니다."}, "critique": ["관심 분야를 나열하는 데 그치고, 각 분야에 대한 본인의 구체적인 기여 의지나 경험이 부족하여 피상적으로 들립니다.", "전반적으로 단조로운 톤과 무표정으로 인해, 지원자가 해당 분야에 대해 진정으로 열정적이라는 인상을 주기 어렵습니다.", "블록체인에 대한 관심 표현이 'playing with softwares'처럼 모호하여, 지원자의 기술적 이해도를 판단하기 어렵습니다."], "key_observations": ["기술 분야에 대한 관심은 있으나, 이를 구체적인 역량으로 연결 짓는 설명이 필요합니다.", "발표 시 열정적인 태도와 자신감 있는 목소리 톤을 보완해야 합니다."]}
```
```json
[12] {"channel": "nonverbal", "t": 31.5, "window_s": 3.0, "state": "neutral", "intensity": 0.3, "note": "시선은 정면을 응시하나, 미세한 표정 변화나 자세의 긴장감이 관찰되지 않음"}
```
```json
[13] {"channel": "nonverbal", "t": 34.5, "window_s": 3.0, "state": "engaged", "intensity": 0.6, "note": "미소와 함께 눈을 마주치며 적극적으로 대화에 참여하려는 모습"}
```
```json
[14] {"channel": "nonverbal", "t": 37.5, "window_s": 3.0, "state": "engaged", "intensity": 0.6, "note": "눈 맞춤 유지, 미세한 미소와 함께 적극적으로 경청하는 듯한 표정"}
```
```json
[15] {"channel": "nonverbal", "t": 40.5, "window_s": 3.0, "state": "engaged", "intensity": 0.6, "note": "눈 맞춤 유지, 미세한 미소와 함께 적극적인 자세"}
```
```json
[16] {"channel": "nonverbal", "t": 42.7340025, "window_s": 1.468004999999998, "state": "nervous", "intensity": 0.6, "note": "시선이 자주 흔들리고, 미세한 목 떨림이 관찰됨"}
```
```json
[17] {"channel": "evaluation", "window_start_s": 32.0, "window_dur_s": 11.468004999999998, "verbal": {"logic": "내용 자체는 명확하게 전달되지만, 문장 구성이 다소 단순하고 단조롭습니다. 'I am an avid reader'와 같은 표현은 흔하게 사용되어 깊이가 부족합니다.", "structure": "문장 구조가 단순하고, 나열식으로 정보를 전달하는 경향이 있습니다. 논리적인 흐름보다는 정보의 나열에 가깝습니다.", "specificity": "취미나 관심사를 언급할 때 구체적인 예시나 경험이 부족하여 추상적인 느낌을 줍니다."}, "vocal": {"volume": "적절한 볼륨을 유지하고 있으나, 전반적으로 힘이 부족하고 단조로운 느낌을 줍니다.", "pace": "말의 속도가 일정하게 유지되지만, 강조가 필요한 부분에서 속도 조절이 미흡합니다.", "pauses": "자연스러운 호흡이나 강조를 위한 멈춤이 부족하여 다소 급하게 느껴집니다.", "intonation": "억양의 변화가 거의 없어 단조롭고 지루하게 들립니다. 감정이나 열정이 느껴지지 않습니다."}, "visual": {"eye_contact": "카메라를 응시하려는 시도는 보이나, 시선이 불안정하거나 초점이 흐트러지는 부분이 있습니다.", "posture": "상체는 비교적 안정적이지만, 어깨나 자세에서 긴장감이 느껴집니다.", "expression": "표정이 다소 무표정하거나 억지로 미소를 짓는 듯한 인상을 줍니다. 진정성이 부족해 보입니다.", "gesture_over_time": "손동작이나 제스처가 거의 없어 시각적인 흥미를 유발하지 못합니다."}, "critique": ["전반적으로 답변의 내용과 전달 방식 모두 평이하고 깊이가 부족합니다. 'avid reader'와 같은 일반적인 표현으로는 지원자의 개성을 어필하기 어렵습니다.", "음성적으로 억양 변화가 거의 없어 단조롭고 지루하게 들립니다. 열정이나 흥미를 전달하려는 노력이 부족해 보입니다.", "시각적으로도 표정이나 제스처가 거의 없어, 답변 내용에 대한 몰입도를 높이는 데 실패했습니다."], "key_observations": ["답변 내용이 너무 일반적이라 면접관에게 깊은 인상을 남기기 어렵습니다.", "목소리 톤과 억양에 변화를 주어 답변에 생동감을 불어넣을 필요가 있습니다.", "자신의 관심사에 대한 구체적인 경험이나 사례를 들어 설명하면 훨씬 설득력이 높아질 것입니다."]}
```

## vid_0033.mp4 — 50.3s, 비언어 17 · 평가 4
지연: 비언어 {'n': 17, 'min': 0.54, 'max': 0.7, 'mean': 0.62} · 평가 {'n': 4, 'min': 3.24, 'max': 6.75, 'mean': 5.73} · end-of-turn 확정 3.83s

```json
[0] {"channel": "nonverbal", "t": 1.5, "window_s": 3.0, "state": "neutral", "intensity": 0.4, "note": "시선은 정면을 응시하나, 미세한 눈 깜빡임과 입술 움직임에서 약간의 긴장감이 느껴짐"}
```
```json
[1] {"channel": "nonverbal", "t": 4.5, "window_s": 3.0, "state": "neutral", "intensity": 0.3, "note": "시선은 정면을 응시하나, 미세한 눈 깜빡임과 어깨의 경직이 관찰됨"}
```
```json
[2] {"channel": "nonverbal", "t": 7.5, "window_s": 3.0, "state": "hesitant", "intensity": 0.6, "note": "말 시작 전 잠시 멈춤, 시선이 불안정하게 움직임"}
```
```json
[3] {"channel": "nonverbal", "t": 10.5, "window_s": 3.0, "state": "engaged", "intensity": 0.6, "note": "시선은 카메라를 응시하고 있으나, 미세한 눈 깜빡임이 관찰됨"}
```
```json
[4] {"channel": "nonverbal", "t": 13.5, "window_s": 3.0, "state": "engaged", "intensity": 0.6, "note": "시선은 카메라를 응시하고 있으나, 미세한 입술 떨림과 약간의 긴장감이 관찰됨"}
```
```json
[5] {"channel": "evaluation", "window_start_s": 0.0, "window_dur_s": 16.0, "verbal": {"logic": "논리적 흐름은 자연스러우나, 문장 구조가 다소 딱딱하고 반복적임.", "structure": "자기소개라는 목적에 충실하게 구성되었으나, 문장 간 연결이 매끄럽지 못함.", "specificity": "전공과 관심 분야를 명확히 언급했으나, 'AI와 컴퓨터 과학의 조합'이 어떤 강점을 주는지에 대한 구체적인 설명이 부족함."}, "vocal": {"volume": "적절한 볼륨을 유지하고 있으나, 전반적으로 힘이 부족하게 들림.", "pace": "말의 속도가 일정하게 유지되려 노력하나, 일부 구간에서 약간의 멈춤이 느껴짐.", "pauses": "문장과 문장 사이의 쉼표가 다소 부자연스럽게 느껴짐.", "intonation": "단조로운 억양으로 인해 지루하게 들릴 수 있음."}, "visual": {"eye_contact": "카메라를 응시하려는 노력이 보이나, 시선이 불안정하게 흔들리는 경향이 있음.", "posture": "정면을 향한 자세는 안정적이나, 어깨가 약간 경직되어 보임.", "expression": "무표정하거나 다소 긴장된 표정으로, 자신감이 부족해 보임.", "gesture_over_time": "손동작이 거의 없어 정적인 인상을 줌."}, "critique": ["전반적으로 답변이 매우 평이하고, 자신감이나 열정이 느껴지지 않아 면접관에게 인상을 남기기 어려움.", "AI와 컴퓨터 과학의 조합이 본인에게 어떤 강점을 주는지에 대한 설명이 추상적이고 모호함.", "단조로운 억양과 경직된 표정은 지원자의 적극성과 열정을 전달하는 데 방해가 됨."], "key_observations": ["자기소개는 기본적인 정보를 전달하는 데는 성공했으나, 깊이가 부족함.", "말의 속도와 억양이 일정하지 않아 지루함을 유발함.", "시선 처리와 표정에서 긴장감이 느껴져 자연스러운 소통이 어려워 보임."]}
```
```json
[6] {"channel": "nonverbal", "t": 16.5, "window_s": 3.0, "state": "engaged", "intensity": 0.6, "note": "시선은 카메라를 응시하고 있으며, 자세는 비교적 안정적임"}
```
```json
[7] {"channel": "nonverbal", "t": 19.5, "window_s": 3.0, "state": "engaged", "intensity": 0.6, "note": "시선은 카메라를 응시하고 있으나, 미세한 눈 깜빡임이 관찰됨"}
```
```json
[8] {"channel": "nonverbal", "t": 22.5, "window_s": 3.0, "state": "engaged", "intensity": 0.6, "note": "시선은 카메라를 응시하고 있으나, 미세한 눈 깜빡임이 관찰됨"}
```
```json
[9] {"channel": "nonverbal", "t": 25.5, "window_s": 3.0, "state": "engaged", "intensity": 0.6, "note": "시선은 카메라를 응시하고 있으나, 미세한 눈 깜빡임이 관찰됨"}
```
```json
[10] {"channel": "nonverbal", "t": 28.5, "window_s": 3.0, "state": "engaged", "intensity": 0.6, "note": "시선은 카메라를 응시하고 있으나, 미세한 눈 깜빡임이 관찰됨"}
```
```json
[11] {"channel": "evaluation", "window_start_s": 16.0, "window_dur_s": 16.0, "verbal": {"logic": "경험 나열에 치중하여 논리적 흐름이 부족함. 'passion'으로 시작하지만 구체적인 성과보다는 활동 나열에 그침.", "structure": "서론-본론-결론의 구조가 명확하지 않고, 경험을 나열하는 방식이라 듣는 사람이 핵심을 파악하기 어려움.", "specificity": "프로젝트 이름(drowsiness detection, sentiment analysis)은 언급했으나, 어떤 기술 스택을 사용했는지, 어떤 성과를 냈는지에 대한 구체성이 매우 부족함."}, "vocal": {"volume": "적절한 편이나, 강조가 부족하여 단조롭게 들림.", "pace": "약간 빠르지만, 내용 전달에 큰 문제는 없음.", "pauses": "자연스러운 호흡과 멈춤이 부족하여 다소 급하게 말하는 인상을 줌.", "intonation": "전반적으로 단조롭고, 흥미를 유발하는 억양 변화가 거의 없음."}, "visual": {"eye_contact": "카메라를 응시하려는 시도는 보이나, 시선이 불안정하고 초점이 흐릿함.", "posture": "정면을 향한 자세는 안정적이나, 어깨가 약간 경직되어 보임.", "expression": "무표정하고 다소 긴장된 듯한 인상.", "gesture_over_time": "손동작이 거의 없어 정적인 느낌을 줌."}, "critique": ["경험 나열에만 치중하고, 각 경험에서 본인이 어떤 역할을 했고 어떤 성과를 냈는지에 대한 설명이 매우 부족함.", "전반적으로 단조로운 톤과 표정으로 인해 면접관의 흥미를 유발하지 못함.", "기술 스택이나 문제 해결 과정에 대한 구체적인 언급이 없어, '무엇을 했는지'만 알 뿐 '어떻게 했는지'는 알 수 없음."], "key_observations": ["경험의 양은 많으나, 질적인 깊이가 부족함.", "자신감 있는 태도보다는 긴장감이 더 느껴짐.", "기술적인 역량을 어필하기 위한 구체적인 사례 제시가 필요함."]}
```
```json
[12] {"channel": "nonverbal", "t": 31.5, "window_s": 3.0, "state": "engaged", "intensity": 0.6, "note": "시선은 정면을 응시하고 있으며, 자세는 비교적 안정적임"}
```
```json
[13] {"channel": "nonverbal", "t": 34.5, "window_s": 3.0, "state": "engaged", "intensity": 0.6, "note": "시선은 카메라를 응시하고 있으나, 미세한 눈 깜빡임이 관찰됨"}
```
```json
[14] {"channel": "nonverbal", "t": 37.5, "window_s": 3.0, "state": "neutral", "intensity": 0.3, "note": "시선은 정면을 응시하나, 미세한 눈 깜빡임과 입술 움직임이 경직된 느낌을 줌"}
```
```json
[15] {"channel": "nonverbal", "t": 40.5, "window_s": 3.0, "state": "neutral", "intensity": 0.3, "note": "시선은 정면을 응시하고 있으나, 미세한 눈 깜빡임과 입술의 긴장이 관찰됨"}
```
```json
[16] {"channel": "nonverbal", "t": 43.5, "window_s": 3.0, "state": "neutral", "intensity": 0.3, "note": "시선은 정면을 응시하나, 미세한 눈 깜빡임과 입술 움직임에서 약간의 긴장감이 느껴짐"}
```
```json
[17] {"channel": "nonverbal", "t": 46.5, "window_s": 3.0, "state": "engaged", "intensity": 0.6, "note": "시선은 카메라를 응시하고 있으나, 미세한 눈 깜빡임이 관찰됨"}
```
```json
[18] {"channel": "evaluation", "window_start_s": 32.0, "window_dur_s": 16.0, "verbal": {"logic": "경험을 나열하는 방식이라 논리적 흐름은 있으나, '개발하고 있다'는 현재 진행형 설명이 다소 모호함.", "structure": "경험-역할-성과-취미 순으로 구성되어 있으나, 각 항목 간의 연결이 매끄럽지 못함.", "specificity": "웹사이트 개발 경험은 언급되었으나, 구체적인 기술 스택이나 성과에 대한 설명이 부족함."}, "vocal": {"volume": "적절한 편이나, 특정 부분에서 볼륨이 미세하게 작아지는 경향이 있음.", "pace": "전반적으로 안정적이나, 정보 전달 시 다소 빠르게 말하는 경향이 있음.", "pauses": "필요한 곳에서 적절한 쉼을 취하고 있으나, 문장 중간에 불필요한 멈춤이 있음.", "intonation": "단조로운 톤으로 인해 내용에 대한 열정이나 자신감이 잘 전달되지 않음."}, "visual": {"eye_contact": "카메라를 응시하려는 노력이 보이나, 시선이 불안정하게 흔들리는 경향이 있음.", "posture": "상체는 안정적이나, 어깨가 다소 경직되어 보임.", "expression": "무표정하거나 다소 긴장된 표정으로, 자신감 있는 인상을 주기 어려움.", "gesture_over_time": "손동작이 거의 없어 정적인 느낌을 줌."}, "critique": ["경험 설명 시 '개발하고 있다'는 표현이 너무 모호하여, 현재 어떤 수준의 역량을 가졌는지 파악하기 어려움.", "전반적으로 단조로운 톤과 무표정으로 인해 답변 내용에 대한 몰입도나 자신감이 부족하게 느껴짐.", "구체적인 성과나 기여도를 수치화하여 설명하지 못해, 경험의 깊이가 얕아 보임."], "key_observations": ["경험 나열 자체는 좋으나, '무엇을', '어떻게' 했는지에 대한 깊이가 부족함.", "면접관에게 자신의 역량을 어필하기 위한 '스토리텔링'이 약함.", "시각적, 청각적 요소 모두에서 '평범함'을 벗어나지 못함."]}
```
```json
[19] {"channel": "nonverbal", "t": 49.1430045, "window_s": 2.286009, "state": "neutral", "intensity": 0.3, "note": "시선은 정면을 응시하고 있으나, 표정 변화가 거의 없어 무표정함."}
```
```json
[20] {"channel": "evaluation", "window_start_s": 48.0, "window_dur_s": 2.286009, "verbal": {"logic": "평범함", "structure": "단조로움", "specificity": "낮음"}, "vocal": {"volume": "적절함", "pace": "보통", "pauses": "없음", "intonation": "단조로움"}, "visual": {"eye_contact": "불안정함", "posture": "뻣뻣함", "expression": "무표정", "gesture_over_time": "없음"}, "critique": ["시선 처리가 불안정하여 면접관과의 소통에 어려움이 느껴짐.", "전반적으로 표정이 무표정하여 자신감이나 열정이 전달되지 않음.", "말의 억양과 속도가 단조로워 지루함을 유발함."], "key_observations": ["전반적으로 준비된 답변이라기보다는 읽는 듯한 인상을 줌.", "자신감 있는 태도와 적극적인 소통 노력이 부족함."]}
```
