# legacy/ — 아카이브 (실험 단계 산출물)

실험/스파이크 단계의 일회용 스크립트와 그 증거를 모아둔 곳. **런타임 모듈과 무관**
(현역 코드는 `src/local_infer/`, 테스트는 `tests/`). 역사·근거 보존용이며, 재실행을 전제로
하지 않는다(경로가 옛 위치를 가리킬 수 있음).

## spikes/ — 스파이크 스크립트 (결정 근거 생성기)
| 파일 | 결정 | 내용 |
|---|---|---|
| `spike_e4b_native_av.py` | D5 | E4B native AV 재검증(audio_url payload, prosody) |
| `spike_cold_prefill.py` | D6 | cold kill-test — periodic prefill 불필요 판명 |
| `spike_visual_fingers.py` | D7 | 다중이미지 시간축 binding 한계 진단 |
| `spike_visual_temporal_v2.py` | D7 | 프레임별+집계 아키텍처 검증 |
| `spike_visual_aggregator.py` | D7 | smart 집계기(naive 집계 echo 한계) |
| `spike_native_video.py` | D8 | video_url 시간축 binding kill-test |
| `spike_video_audio.py` | D8 | video_url 단독 → 오디오 native 로드 여부("NO AUDIO") |

주: 일부 스파이크는 `from local_infer.native_audio import ...`에 의존(그 util은 런타임 경로에선
미사용이나 아카이브 스파이크 때문에 `src/`에 잔존). 재실행 시 `PYTHONPATH=src`.

## evidence/ — 과거 실측 증거 (JSON)
`phase3-prefill-effect`(철회된 best-case), `spike-cold-prefill`, `spike-e4b-native-av`,
`spike-visual-{fingers,temporal-v2,aggregator}`, `spike-native-video`,
`spike-video-audio{,-combo}`. 결정별 해석은 `docs/DECISIONS.md` D5–D8.

(현재 모듈 증거 `m2-window-eval.json`·`m5-e2e.json`은 `.sisyphus/evidence/`에 있음 — 여기 아님.)
