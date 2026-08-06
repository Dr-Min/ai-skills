# timed-storyboard

> 이야기·트리트먼트·대본을 초 단위 쇼트와 인물·소품·시선·카메라 동선이 명시된 시네마틱 스토리보드 계획으로 바꿉니다.

[전체 스킬 목록](../../README.md) · [실행 지침](SKILL.md)

## 해결하는 문제

한 장의 예쁜 콘셉트 이미지만으로는 쇼트 안에서 누가 언제 움직이고, 어디를 바라보고, 소품이 어떻게 전달되며, 카메라가 어떤 경로로 이동하는지 알 수 없습니다. 이 스킬은 모든 변화를 프레임과 좌표, 액션 단계로 기록해 영상 생성이나 촬영 전에 모호함을 줄입니다.

## 이런 요청에 사용합니다

- “이 30초 이야기를 쇼트별로 나누고 정확한 시간을 잡아줘.”
- “인물이 방을 가로질러 새장에 손을 대는 동선을 그려줘.”
- “시작·중간·끝 자세와 카메라 이동이 보이는 러프보드를 만들어줘.”
- “AI 영상 파이프라인에 넘길 JSON과 CSV도 같이 만들어줘.”

음악의 비트나 공격음을 분석해 컷을 정하는 작업은 하지 않습니다. 그 목적에는 `sync-cuts-to-music`을 별도로 사용합니다.

## 스토리 잠금

이미지를 만들기 전에 다음 여섯 요소를 문장으로 고정합니다.

- 원인: 무엇 때문에 사건이 시작되는가
- 목표: 주인공이 무엇을 원하는가
- 대가: 실패하면 무엇을 잃는가
- 장애물: 무엇이 목표를 막는가
- 발견: 무엇을 새롭게 알아차리는가
- 선택: 마지막에 어떤 행동을 선택하는가

각 장면은 이 이야기 구조에서 눈에 보이는 변화를 하나 이상 담당해야 합니다.

## 작업 흐름

1. 이야기 계약과 목표 길이, 화면비, FPS를 정합니다.
2. 전체를 장면·쇼트·액션 단계로 나누고 정수 프레임을 시간 기준으로 사용합니다.
3. 인물, 소품, 카메라와 환경 요소의 경로를 각각 기록합니다.
4. timed shot list와 blocking summary를 먼저 승인받습니다.
5. 선택한 러프니스 레벨로 보드를 생성합니다.
6. 실제 이미지에서 화살표, 고스트 위치, 시선, 접촉, 출입과 카메라 축을 확인합니다.
7. JSON을 검증하고 README·CSV·요약 파일을 내보냅니다.

## 네 가지 보드 수준

| 레벨 | 용도 |
|---|---|
| 1 | 빠른 썸네일과 구도 탐색 |
| 2 | 기본 러프 스토리보드, 기본값 |
| 3 | 제작용 상세 보드와 복잡한 동선 |
| 4 | 깨끗한 콘셉트 스틸 + 별도 모션 카드 |

비교 이미지는 [`assets/storyboard-levels-1-4.png`](assets/storyboard-levels-1-4.png)에 있습니다.

## 설치와 명령

```bash
python install.py --no-law-mcp --skills timed-storyboard
```

```powershell
python skills/timed-storyboard/scripts/storyboard_plan.py init `
  --output project-dir --title "My Film" --duration 15 --fps 24 --level 2

python skills/timed-storyboard/scripts/storyboard_plan.py validate `
  --plan project-dir/storyboard_plan.json

python skills/timed-storyboard/scripts/storyboard_plan.py export `
  --plan project-dir/storyboard_plan.json --output project-dir
```

## 결과물

- `storyboard_plan.json`: 프레임 기반 원본 계획
- 프로젝트 `README.md`: 사람용 전체 설명과 보드 이미지
- `timing_summary.md`: 장면과 쇼트 시간 요약
- `shotlist.csv`: 쇼트 목록
- `action_timeline.csv`: 액션 단계
- `motion_paths.csv`: 인물·소품·카메라 경로

## 포함 파일

```text
timed-storyboard/
├─ SKILL.md
├─ README.md
├─ assets/storyboard-levels-1-4.png
├─ references/
│  ├─ motion-notation.md
│  ├─ output-contract.md
│  └─ roughness-levels.md
└─ scripts/storyboard_plan.py
```

## 완료 기준

- 모든 쇼트에 보이는 변화 또는 의도된 정지가 있음
- 쇼트 시간이 겹치지 않고 전체 길이에 정확히 맞음
- 움직이는 모든 대상과 카메라에 경로 또는 정지 선언이 있음
- 시선, 소품 이동, 배우 이동, 카메라 이동을 서로 분리함
- 선택한 보드 수준과 실제 이미지가 일치함
- JSON과 사람용 내보내기 파일이 모두 검증됨
