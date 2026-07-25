# higgs-skills

Claude Cowork용 스킬 모음 저장소. 히그스필드(Higgsfield) Cinema Studio AI 영화 제작
파이프라인 강의를 스킬로 만든 것과, 초보자용 스킬 제작 가이드 스킬이 들어 있습니다.

## 📦 무엇이 들어 있나

| 항목 | 설명 |
| --- | --- |
| **`cinema-studio-pipeline/`** | 히그스필드 "The AI Filmmaking Pipeline" 강의(22레슨) 기반 스킬. 아이디어 → Seedance 완성 샷까지의 제작 방법론을 Claude가 그대로 적용하도록 함 |
| **`cinema-studio-pipeline.skill`** | 위 스킬의 설치용 패키지 (Cowork에서 **Save skill**) |
| **`cinema-studio-pro-raw.md`** | 강의 22레슨 **원문 전문** (스크랩 보존본) |
| **`cinema-studio-pro-상세해설.md`** | 원문 전문을 한국어로 한 대목씩 풀어쓴 **상세 해설서** |
| **`skill-builder-101/`** | **초보자용 스킬 제작 스킬.** 스킬 개념부터 SKILL.md 작성·트리거·MCP 연동·패키징·배포까지 |
| **`skill-builder-101.skill`** | 위 스킬의 설치용 패키지 |

## 🎬 cinema-studio-pipeline

히그스필드 헬 그라인드 팀의 제작 파이프라인을 인코딩한 스킬입니다.

- **4단계 파이프라인**: Think(프롬프트) → Setup(프로젝트·명명) → Generation(로케이션·캐릭터) → Seedance(모션 테스트)
- **핵심 기준**: "약속이 아니라 증거(픽셀로 판단)", 25~30% 포트레이트 규칙, 원본에 마스킹 편집, 한 변수씩 테스트, slop 감별
- **참고파일 구성**: 파이프라인·프롬프트·모델선택·로케이션·캐릭터·Seedance/slop·캡스톤 + 강의 원문 아카이브

캐릭터시트 만들기, 로케이션 생성, 프롬프트 최적화, 모델 선택, slop 감별 등을 물어보면 Claude가
강의 기준대로 도와줍니다.

## 🛠 skill-builder-101

"스킬을 어떻게 만드는지" 자체를 가르치는 초보자용 스킬입니다.

- 스킬이 무엇인지(훈련이 아니라 "미리 써둔 매뉴얼")
- SKILL.md 구조 · frontmatter · progressive disclosure
- `description`으로 트리거 잡는 법 (자주 하는 실수 포함)
- **MCP 도구 연동법** (이미 연결된 MCP 쓰기 / 커넥터 연결 안내 / 플러그인으로 배포)
- `.skill` 패키징 · 설치 · git·플러그인 배포
- 통째로 베낄 수 있는 완성 예시 3종

## 🚀 스킬 설치법

1. Cowork에서 해당 `.skill` 파일을 열면 카드에 **Save skill** 버튼이 표시됩니다.
2. 누르면 내 프로필에 설치됩니다.
3. 관련 주제로 대화하면 Claude가 자동으로 해당 스킬을 켭니다.
4. 관리·삭제는 앱 **설정 > Capabilities**에서.

> 스킬은 Claude가 필요할 때 펼쳐 읽는 "매뉴얼"입니다. 히그스필드 웹사이트 안에서 자동 실행되는
> 것이 아니라, **Claude와 대화하며 작업할 때** 그 기준대로 돕는 방식으로 동작합니다.

## 📁 폴더 구조

```
higgs-skills/
├── README.md
├── cinema-studio-pipeline/
│   ├── SKILL.md
│   └── references/            # 01~07 실무 가이드 + course-archive.md(원문 전문)
├── cinema-studio-pipeline.skill
├── cinema-studio-pro-raw.md
├── cinema-studio-pro-상세해설.md
├── skill-builder-101/
│   ├── SKILL.md
│   └── references/            # anatomy · writing-guide · mcp-integration · packaging · examples
└── skill-builder-101.skill
```

## 📝 출처

`cinema-studio-*` 자료는 히그스필드 아카데미 강의
[The AI Filmmaking Pipeline](https://higgsfield.ai/academy/courses/cinema-studio-pro)를
학습·정리한 것입니다. 개인 학습·참고용.

---

_Made with Claude Cowork._
