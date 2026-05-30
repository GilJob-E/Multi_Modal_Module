# 윈도우별 리턴값 — 실측 원본 (M5, 백그라운드 파이프라인 + compact tail)

백그라운드 3-레인 + end-of-turn **compact tail**(D9, 2026-05-30 실측). 채널①(비언어)·②(평가) 둘 다
변별 강제. 발화 중 풀 윈도우는 백그라운드 독립 추론(채널① 안 막음), end-of-turn은 답변 *마지막 구간*만
compact(summary+critique)로 평가해 확정 지연을 묶는다. per-window 리턴값 전체, 해석 없음.
신호는 타임스탬프순 정렬(완료순 아님). 증거: `.sisyphus/evidence/m5-e2e.json`.


## vid_0001.mp4 — 43.5s, 비언어 15 · 평가 3(풀 2 + compact tail 1)
지연: 비언어 {'n': 15, 'min': 0.53, 'max': 0.75, 'mean': 0.65} · 풀평가 {'n': 2, 'min': 6.4, 'max': 7.9, 'mean': 7.15} · compact tail {'n': 1, 'min': 0.87, 'max': 0.87, 'mean': 0.87} · **end-of-turn 확정 0.87s ✓(목표 ≤2.5s)**

```json
[0] {"channel": "evaluation", "window_start_s": 0.0, "window_dur_s": 16.0, "verbal": {"logic": "자기소개는 명확하게 전달되지만, 'tech enthusiast'와 같은 일반적인 표현에 머물러 있어 깊이가 부족합니다.", "structure": "전형적인 자기소개 구조를 따르고 있어 안정적입니다.", "specificity": "전공과 학교는 구체적이지만, 관심 분야에 대한 설명이 피상적입니다."}, "vocal": {"volume": "적절한 볼륨을 유지하고 있습니다.", "pace": "전반적으로 안정적인 속도를 유지하고 있으나, 일부 구간에서 약간의 망설임이 느껴집니다.", "pauses": "자연스러운 호흡과 쉼을 사용하고 있습니다.", "intonation": "전반적으로 평이한 톤으로, 열정이나 자신감을 강조하는 억양이 부족합니다."}, "visual": {"eye_contact": "카메라를 응시하려는 노력이 보이나, 시선이 약간 불안정합니다.", "posture": "상체는 안정적으로 보이나, 어깨가 약간 경직되어 보입니다.", "expression": "표정은 무난하지만, 자신감이나 흥미를 드러내는 역동성이 부족합니다.", "gesture_over_time": "손동작이 거의 없어 다소 정적입니다."}, "critique": ["자기소개 내용이 너무 일반적입니다. 'tech enthusiast'라는 표현 대신, 구체적으로 어떤 기술에 관심이 있는지 언급하여 전문성을 보여줘야 합니다.", "전반적인 톤이 너무 평이하고 단조롭습니다. 본인의 열정을 보여줄 수 있는 억양 변화나 강조가 필요합니다.", "시선 처리가 다소 불안정하여 자신감이 부족해 보입니다. 카메라를 정면으로 응시하며 안정감을 주어야 합니다."], "key_observations": ["기본적인 자기소개는 잘 수행했습니다.", "전공과 학교 정보는 명확하게 전달되었습니다.", "내용의 깊이와 표현의 역동성이 부족합니다."], "compact": false}
```
```json
[1] {"channel": "nonverbal", "t": 1.5, "window_s": 3.0, "state": "neutral", "intensity": 0.3, "note": "시선은 정면을 응시하나, 미세한 눈 깜빡임과 입술 움직임에서 약간의 긴장감이 느껴짐"}
```
```json
[2] {"channel": "nonverbal", "t": 4.5, "window_s": 3.0, "state": "neutral", "intensity": 0.3, "note": "시선은 정면을 응시하나, 미세한 눈 깜빡임과 입술 움직임이 관찰됨"}
```
```json
[3] {"channel": "nonverbal", "t": 7.5, "window_s": 3.0, "state": "neutral", "intensity": 0.3, "note": "시선은 정면을 응시하나, 미세한 눈 깜빡임과 입술 움직임에서 약간의 긴장감이 느껴짐"}
```
```json
[4] {"channel": "nonverbal", "t": 10.5, "window_s": 3.0, "state": "neutral", "intensity": 0.3, "note": "시선은 정면을 응시하나, 미세한 표정 변화나 자세의 긴장감이 관찰되지 않음"}
```
```json
[5] {"channel": "nonverbal", "t": 13.5, "window_s": 3.0, "state": "engaged", "intensity": 0.6, "note": "눈 맞춤 유지, 미세한 미소와 함께 적극적인 자세"}
```
```json
[6] {"channel": "evaluation", "window_start_s": 16.0, "window_dur_s": 16.0, "verbal": {"logic": "AI와 머신러닝에 대한 관심 표명 후, 블록체인과 탈중앙화 앱으로 관심사를 확장하는 흐름은 논리적입니다. 하지만 'exploring the realm of blockchain'과 같은 표현은 다소 추상적입니다.", "structure": "관심 분야를 나열하는 구조는 명확하나, 각 분야에 대한 깊이 있는 설명 없이 나열식으로 끝나는 경향이 있습니다.", "specificity": "AI와 머신러닝은 언급되었으나, 블록체인에 대한 관심이 'playing with softwares'라는 다소 모호한 표현으로 마무리되어 구체성이 떨어집니다."}, "vocal": {"volume": "적절한 볼륨을 유지하고 있으나, 전반적으로 힘이 부족하게 들립니다.", "pace": "말의 속도는 안정적이지만, 특정 단어에서 약간의 망설임이 느껴집니다.", "pauses": "자연스러운 호흡을 위한 멈춤은 있으나, 문장 전환 시의 멈춤이 다소 부자연스럽습니다.", "intonation": "전반적으로 단조로운 톤으로, 관심 분야에 대한 열정이나 흥미가 충분히 전달되지 않습니다."}, "visual": {"eye_contact": "카메라를 응시하려는 시도는 보이나, 시선이 불안정하게 흔들리는 경향이 있습니다.", "posture": "상체는 비교적 안정적이나, 어깨가 약간 경직되어 보입니다.", "expression": "표정은 무표정에 가깝고, 관심 분야에 대한 진정성 있는 흥미를 보여주지 못합니다.", "gesture_over_time": "손동작이나 제스처가 거의 없어, 전달하고자 하는 내용에 대한 몰입도가 낮아 보입니다."}, "critique": ["관심 분야를 나열하는 데 그치고, 각 분야에 대한 본인의 구체적인 기여 의지나 경험이 부족하여 피상적으로 들립니다.", "전반적으로 단조로운 톤과 무표정으로 인해, 지원자가 해당 분야에 대해 진정으로 열정적이라는 인상을 주기 어렵습니다.", "블록체인에 대한 관심 표현이 'playing with softwares'처럼 모호하여, 지원자의 기술적 이해도를 판단하기 어렵습니다."], "key_observations": ["기술 분야에 대한 관심은 있으나, 이를 구체적인 역량으로 연결 짓는 설명이 필요합니다.", "발표 시 열정적인 태도와 자신감 있는 목소리 톤을 보완해야 합니다."], "compact": false}
```
```json
[7] {"channel": "nonverbal", "t": 16.5, "window_s": 3.0, "state": "engaged", "intensity": 0.6, "note": "눈 맞춤 유지, 미세한 미소와 함께 적극적인 경청 태도 보임"}
```
```json
[8] {"channel": "nonverbal", "t": 19.5, "window_s": 3.0, "state": "neutral", "intensity": 0.3, "note": "시선은 정면을 응시하나, 미세한 표정 변화나 자세의 변화는 관찰되지 않음"}
```
```json
[9] {"channel": "nonverbal", "t": 22.5, "window_s": 3.0, "state": "engaged", "intensity": 0.6, "note": "시선은 카메라를 응시하고 있으나, 미세한 입술 떨림과 약간의 긴장감이 보임"}
```
```json
[10] {"channel": "nonverbal", "t": 25.5, "window_s": 3.0, "state": "neutral", "intensity": 0.3, "note": "표정 변화가 거의 없고 시선이 정면을 응시하고 있으나, 미세한 긴장감이 느껴짐"}
```
```json
[11] {"channel": "nonverbal", "t": 28.5, "window_s": 3.0, "state": "neutral", "intensity": 0.3, "note": "시선이 정면을 응시하고 있으나, 표정 변화가 거의 없어 중립적임"}
```
```json
[12] {"channel": "nonverbal", "t": 31.5, "window_s": 3.0, "state": "neutral", "intensity": 0.3, "note": "시선은 정면을 응시하나, 미세한 표정 변화나 자세의 긴장감이 관찰되지 않음"}
```
```json
[13] {"channel": "evaluation", "window_start_s": 32.0, "window_dur_s": 11.468004999999998, "verbal": {}, "vocal": {}, "visual": {}, "critique": ["구체적인 목표나 계획이 부족함", "자기소개에 그치는 느낌"], "key_observations": ["독서와 여행을 즐기며 새로운 경험을 하고 싶다는 포부를 밝힘."], "compact": true}
```
```json
[14] {"channel": "nonverbal", "t": 34.5, "window_s": 3.0, "state": "engaged", "intensity": 0.6, "note": "미소와 함께 눈을 마주치며 적극적으로 대화에 참여하려는 모습"}
```
```json
[15] {"channel": "nonverbal", "t": 37.5, "window_s": 3.0, "state": "engaged", "intensity": 0.6, "note": "눈 맞춤 유지, 미세한 미소와 함께 적극적으로 경청하는 듯한 표정"}
```
```json
[16] {"channel": "nonverbal", "t": 40.5, "window_s": 3.0, "state": "engaged", "intensity": 0.6, "note": "눈 맞춤 유지, 미세한 미소와 함께 적극적으로 경청하는 듯한 표정"}
```
```json
[17] {"channel": "nonverbal", "t": 42.7340025, "window_s": 1.468004999999998, "state": "nervous", "intensity": 0.6, "note": "시선이 자주 흔들리고, 미세한 목 떨림이 관찰됨"}
```

## vid_0033.mp4 — 50.3s, 비언어 17 · 평가 4(풀 3 + compact tail 1)
지연: 비언어 {'n': 17, 'min': 0.55, 'max': 0.72, 'mean': 0.64} · 풀평가 {'n': 3, 'min': 7.41, 'max': 7.53, 'mean': 7.48} · compact tail {'n': 1, 'min': 0.72, 'max': 0.72, 'mean': 0.72} · **end-of-turn 확정 0.72s ✓(목표 ≤2.5s)**

```json
[0] {"channel": "evaluation", "window_start_s": 0.0, "window_dur_s": 16.0, "verbal": {"logic": "논리적 흐름은 자연스러우나, 문장 구조가 다소 딱딱하고 반복적임.", "structure": "자기소개라는 목적에 충실하게 구성되었으나, 문장 간 연결이 매끄럽지 못함.", "specificity": "전공과 관심 분야를 명확히 언급했으나, 'AI와 컴퓨터 과학의 조합'이 어떤 강점을 주는지에 대한 구체적인 설명이 부족함."}, "vocal": {"volume": "적절한 볼륨을 유지하고 있으나, 전반적으로 힘이 부족하게 들림.", "pace": "말의 속도가 일정하게 유지되려 노력하나, 일부 구간에서 약간의 멈춤이 느껴짐.", "pauses": "문장과 문장 사이의 쉼이 다소 부자연스럽고, 생각하는 듯한 멈춤이 있음.", "intonation": "단조로운 억양으로 인해 지루하게 들릴 수 있음. 강조가 필요한 부분에서 억양 변화가 부족함."}, "visual": {"eye_contact": "카메라를 응시하려는 노력이 보이나, 시선이 불안정하게 흔들리는 경향이 있음.", "posture": "정면을 향한 자세는 안정적이나, 어깨가 약간 경직되어 보임.", "expression": "무표정하거나 다소 긴장된 표정으로, 자신감 있는 인상을 주기 어려움.", "gesture_over_time": "손동작이 거의 없어 정적인 느낌을 줌."}, "critique": ["전반적으로 답변이 매우 평이하고, 면접관에게 깊은 인상을 남기기에는 내용의 깊이가 부족함.", "억양과 표정이 단조로워, 자기소개라는 중요한 순간에 에너지를 전달하지 못하고 있음.", "AI와 컴퓨터 과학의 조합이 '어떤 강점'을 주는지에 대한 구체적인 설명이 없어, 추상적인 주장으로만 들림."], "key_observations": ["자기소개는 기본적인 요소를 갖추었으나, 차별화된 강점을 어필하지 못함.", "발표 시 긴장감이 억양과 표정에 그대로 드러나고 있음.", "문장 구조가 딱딱하여, 자연스러운 대화보다는 '읽는 듯한' 느낌을 줌."], "compact": false}
```
```json
[1] {"channel": "nonverbal", "t": 1.5, "window_s": 3.0, "state": "neutral", "intensity": 0.4, "note": "시선은 정면을 응시하나, 미세한 눈 깜빡임과 입술 움직임에서 약간의 긴장감이 느껴짐"}
```
```json
[2] {"channel": "nonverbal", "t": 4.5, "window_s": 3.0, "state": "neutral", "intensity": 0.3, "note": "시선은 정면을 응시하나, 미세한 눈 깜빡임과 어깨의 경직이 관찰됨"}
```
```json
[3] {"channel": "nonverbal", "t": 7.5, "window_s": 3.0, "state": "hesitant", "intensity": 0.6, "note": "말 시작 전 잠시 멈춤, 시선이 약간 불안정하게 움직임"}
```
```json
[4] {"channel": "nonverbal", "t": 10.5, "window_s": 3.0, "state": "engaged", "intensity": 0.6, "note": "시선은 카메라를 응시하고 있으나, 미세한 눈 깜빡임이 관찰됨"}
```
```json
[5] {"channel": "nonverbal", "t": 13.5, "window_s": 3.0, "state": "engaged", "intensity": 0.6, "note": "시선은 카메라를 응시하고 있으며, 자세는 비교적 안정적임"}
```
```json
[6] {"channel": "evaluation", "window_start_s": 16.0, "window_dur_s": 16.0, "verbal": {"logic": "경험 나열에 치중하여 논리적 흐름이 부족함. 'passion'으로 시작하지만 구체적인 성과보다는 활동 나열에 그침.", "structure": "서론-본론-결론의 구조가 명확하지 않고, 경험을 나열하는 방식이라 듣는 사람이 핵심을 파악하기 어려움.", "specificity": "프로젝트 이름(drowsiness detection, sentiment analysis)은 언급했으나, 어떤 기술 스택을 사용했는지, 어떤 성과를 냈는지에 대한 구체성이 매우 부족함."}, "vocal": {"volume": "적절한 편이나, 긴장감으로 인해 약간 작게 들림.", "pace": "약간 빠르고 급하게 말하는 경향이 있어, 내용 전달에 집중하기 어려움.", "pauses": "자연스러운 호흡이나 강조를 위한 멈춤이 부족함.", "intonation": "단조롭고 평이한 톤으로, 내용에 대한 열정이나 자신감이 잘 드러나지 않음."}, "visual": {"eye_contact": "카메라를 응시하려 노력하지만, 시선이 불안정하게 흔들림.", "posture": "정면을 향한 자세는 안정적이나, 어깨가 약간 경직되어 보임.", "expression": "무표정하거나 다소 긴장된 표정으로, 자신감이나 흥미가 잘 전달되지 않음.", "gesture_over_time": "손동작이 거의 없어, 내용에 대한 몰입도가 낮아 보임."}, "critique": ["경험 나열식 답변으로, '무엇을 했는지'보다 '어떤 역량을 가졌는지'를 보여주는 데 실패함.", "프로젝트 경험을 설명할 때, 사용 기술 스택이나 본인의 기여도를 구체적으로 언급하지 않아 깊이가 없어 보임.", "전반적으로 답변의 톤이 단조롭고, 내용에 대한 열정이나 자신감이 부족하게 느껴짐."], "key_observations": ["경험 자체는 나열했지만, 그 경험을 통해 무엇을 배웠고 어떤 성과를 냈는지에 대한 설명이 부족함.", "말의 속도가 빠르고 톤이 단조로워, 면접관이 집중하기 어려움.", "자신감 있는 태도와 표정 연기가 필요함."], "compact": false}
```
```json
[7] {"channel": "nonverbal", "t": 16.5, "window_s": 3.0, "state": "engaged", "intensity": 0.6, "note": "시선은 카메라를 응시하고 있으나, 미세한 눈 깜빡임이 관찰됨"}
```
```json
[8] {"channel": "nonverbal", "t": 19.5, "window_s": 3.0, "state": "engaged", "intensity": 0.6, "note": "시선은 정면을 응시하고 있으며, 자세는 비교적 안정적임"}
```
```json
[9] {"channel": "nonverbal", "t": 22.5, "window_s": 3.0, "state": "engaged", "intensity": 0.6, "note": "시선은 카메라를 응시하고 있으나, 미세한 눈 깜빡임이 관찰됨"}
```
```json
[10] {"channel": "nonverbal", "t": 25.5, "window_s": 3.0, "state": "engaged", "intensity": 0.6, "note": "시선은 카메라를 응시하고 있으나, 미세한 눈 깜빡임이 관찰됨"}
```
```json
[11] {"channel": "nonverbal", "t": 28.5, "window_s": 3.0, "state": "engaged", "intensity": 0.6, "note": "시선은 카메라를 응시하고 있으나, 미세한 눈 깜빡임이 관찰됨"}
```
```json
[12] {"channel": "nonverbal", "t": 31.5, "window_s": 3.0, "state": "engaged", "intensity": 0.6, "note": "시선은 정면을 응시하고 있으며, 자세는 비교적 안정적임"}
```
```json
[13] {"channel": "evaluation", "window_start_s": 32.0, "window_dur_s": 16.0, "verbal": {"logic": "경험을 나열하는 방식은 좋으나, 각 경험에서 어떤 성과를 냈는지에 대한 구체적인 설명이 부족합니다. '개발하고 있다', '관리하고 있다'는 현재 진행형의 상태만 전달할 뿐, 기여도를 명확히 보여주지 못합니다.", "structure": "경험을 나열하는 구조는 명확하나, 문장 연결이 다소 어색하고 자연스럽지 못합니다. 문장 간의 흐름이 매끄럽지 못하고, 정보 전달에 치중되어 있어 듣는 사람이 내용을 따라가기 어렵습니다.", "specificity": "웹사이트 개발이나 팀 관리에 대한 언급은 있으나, 어떤 기술 스택을 사용했는지, 어떤 종류의 웹사이트를 만들었는지, 팀 관리를 통해 어떤 문제를 해결했는지 등 구체적인 정보가 매우 부족합니다."}, "vocal": {"volume": "적절한 편이나, 특정 부분에서 목소리가 작아지는 경향이 있습니다.", "pace": "전반적으로 빠르지만, 중요한 내용을 전달할 때 속도를 조절하는 노력이 보이지 않습니다.", "pauses": "문장과 문장 사이의 호흡이 다소 짧아, 내용이 급하게 쏟아져 나오는 느낌을 줍니다.", "intonation": "단조로운 톤으로 말하고 있어, 내용에 대한 열정이나 자신감이 잘 전달되지 않습니다."}, "visual": {"eye_contact": "카메라를 응시하려는 시도는 보이나, 시선이 불안정하게 흔들리는 경향이 있습니다.", "posture": "상체는 비교적 곧게 세우고 있으나, 어깨가 약간 경직되어 보입니다.", "expression": "표정은 무표정에 가깝고, 답변 내용에 대한 몰입도가 낮아 보입니다.", "gesture_over_time": "손동작이나 제스처가 거의 없어, 답변에 생동감이 부족합니다."}, "critique": ["경험을 나열하는 데 그치고, 본인의 기여도나 성과를 수치화하거나 구체적으로 설명하지 못하는 점이 가장 큰 약점입니다.", "전반적으로 단조롭고 급하게 말하는 톤이 답변의 신뢰도와 자신감을 떨어뜨립니다.", "경험을 설명할 때 'basically'와 같은 불필요한 부사를 자주 사용하여 전문성이 떨어져 보입니다."], "key_observations": ["경험 자체는 나쁘지 않으나, 이를 '어떻게' 했는지에 대한 설명이 전무합니다.", "면접관에게 '나는 이 일을 잘했다'는 인상을 주기에는 내용이 너무 추상적입니다."], "compact": false}
```
```json
[14] {"channel": "nonverbal", "t": 34.5, "window_s": 3.0, "state": "engaged", "intensity": 0.6, "note": "시선은 카메라를 응시하고 있으나, 미세한 눈 깜빡임이 관찰됨"}
```
```json
[15] {"channel": "nonverbal", "t": 37.5, "window_s": 3.0, "state": "neutral", "intensity": 0.3, "note": "시선은 정면을 응시하나, 미세한 눈 깜빡임과 입술 움직임이 경직된 느낌을 줌"}
```
```json
[16] {"channel": "nonverbal", "t": 40.5, "window_s": 3.0, "state": "neutral", "intensity": 0.3, "note": "시선은 정면을 응시하고 있으나, 미세한 표정 변화나 자세의 긴장감이 관찰되지 않음"}
```
```json
[17] {"channel": "nonverbal", "t": 43.5, "window_s": 3.0, "state": "neutral", "intensity": 0.3, "note": "시선은 정면을 응시하나, 미세한 눈 깜빡임과 입술 움직임에서 약간의 긴장감이 느껴짐"}
```
```json
[18] {"channel": "nonverbal", "t": 46.5, "window_s": 3.0, "state": "engaged", "intensity": 0.6, "note": "시선은 카메라를 응시하고 있으나, 미세한 눈 깜빡임이 관찰됨"}
```
```json
[19] {"channel": "evaluation", "window_start_s": 48.0, "window_dur_s": 2.286009, "verbal": {}, "vocal": {}, "visual": {}, "critique": ["약점 극복 노력이 추상적임", "구체적인 사례 부족"], "key_observations": ["지원자는 자신의 강점과 약점을 솔직하게 이야기하며 성장 의지를 보였다."], "compact": true}
```
```json
[20] {"channel": "nonverbal", "t": 49.1430045, "window_s": 2.286009, "state": "neutral", "intensity": 0.3, "note": "시선은 정면을 응시하나, 미세한 눈 깜빡임과 경직된 표정이 관찰됨"}
```
