# sync-cuts-to-music

> 균일한 BPM 격자가 아니라 음원의 실제 트랜지언트와 공격음을 분석해 컷 지점을 제안하고, 검토 가능한 편집 패키지 또는 CapCut JSON 초안을 만듭니다.

[전체 스킬 목록](../../README.md) · [실행 지침](SKILL.md)

## 해결하는 문제

음악 편집에서 모든 박자에 기계적으로 자르면 실제 필, 드럼 공격, 전환과 어긋날 수 있습니다. 이 스킬은 스펙트럴 플럭스와 RMS 공격을 사용해 컷 후보를 찾고, 프레임 단위로 반올림된 정확한 시점과 선택 근거를 시각화합니다.

## 이런 요청에 사용합니다

- “음악의 빠른 필 구간에 이미지가 바뀌게 해줘.”
- “4~6초 근처에서 실제 공격음이 어디인지 보여줘.”
- “컷 선택 근거가 보이는 그래프와 편집 패키지를 만들어줘.”
- “검토한 컷을 CapCut에서 이어서 편집할 수 있게 초안을 만들어줘.”

## 두 가지 출력 모드

### Split package

버전 독립적인 기본 결과입니다. 번호가 붙은 무음 비주얼 클립, 연속 오디오, 컷 타이밍 CSV·JSON, 진단 PNG, 기준 MP4와 manifest를 만듭니다.

### CapCut JSON

Split package를 먼저 만든 뒤 사용자가 고른 호환 템플릿을 복제하고, 복사본의 JSON에 동일한 클립과 오디오를 배치합니다. 버전과 스키마에 민감한 실험 기능이며 live draft를 직접 수정하지 않습니다.

## 작업 흐름

1. 원본 음원, 영상, 이미지와 CapCut draft를 보존합니다.
2. `doctor`로 Python 의존성과 FFmpeg를 확인합니다.
3. `analyze`로 컷 계획 JSON을 만듭니다.
4. `visualize`로 공격 강도와 컷·릴리스 지점을 표시합니다.
5. 사용자에게 진단 이미지를 보여주고 컷을 승인받습니다.
6. 승인된 계획으로 전체 split package를 렌더합니다.
7. 필요한 경우 복제한 템플릿에 CapCut JSON을 생성합니다.
8. 프레임 수, 길이, 파일 해시와 참조 무결성을 검증합니다.

## 설치

```bash
python install.py --no-law-mcp --skills sync-cuts-to-music
python skills/sync-cuts-to-music/scripts/beat_cut.py doctor
```

Python과 FFmpeg가 필요합니다. FFmpeg가 `PATH`에 없다면 명령에 `--ffmpeg` 경로를 전달할 수 있습니다.

## 분석 예시

```powershell
python skills/sync-cuts-to-music/scripts/beat_cut.py analyze `
  --audio music.wav `
  --duration 15 `
  --hint 4:6 `
  --hint 9: `
  --zoom medium `
  --color cycle `
  --output cut_plan.json

python skills/sync-cuts-to-music/scripts/beat_cut.py visualize `
  --audio music.wav `
  --plan cut_plan.json `
  --output cut_diagnostic.png
```

힌트 구간은 검색 범위 안내일 뿐 정확한 컷으로 강제하지 않습니다. 실제 공격음과 첫 합법 렌더 프레임을 기준으로 최종 시점을 계산합니다.

## 주요 결과물

- `cut_plan.json`: 원본 해시, 설정, 검출 시점, 렌더 프레임과 릴리스 근거
- `cut_diagnostic.png`: 컷·릴리스·후보·공격 강도 시각화
- 번호가 붙은 분할 비주얼 클립과 연속 오디오
- 타이밍 CSV·JSON, manifest, 기준 MP4
- 선택 시 staged CapCut draft 복사본

## 포함 파일

```text
sync-cuts-to-music/
├─ SKILL.md
├─ README.md
├─ references/
│  ├─ algorithm.md
│  ├─ capcut-json.md
│  └─ output-contract.md
└─ scripts/
   ├─ beat_cut.py
   ├─ beatcut_core.py
   └─ test_beat_cut.py
```

## 한계와 안전 경계

- 흰색 플래시는 기본으로 사용하지 않으며 빠른 점멸 위험을 경고합니다.
- CapCut이 완전히 종료되지 않은 상태에서 live draft를 수정하지 않습니다.
- JSON이 파싱되고 참조가 맞아도 실제 설치된 CapCut에서 열리고 재생되기 전에는 완전 검증으로 간주하지 않습니다.
- 음악 분석 없이 이야기 시간을 설계하려면 `timed-storyboard`를 사용합니다.
