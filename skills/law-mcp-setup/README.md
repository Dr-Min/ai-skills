# law-mcp-setup

> 법제처 국가법령정보센터 Open API 인증값을 안전하게 등록하고 Korean Law MCP를 Codex에 연결·복구·검증합니다.

[전체 스킬 목록](../../README.md) · [실행 지침](SKILL.md) · [연결 구조](../../docs/law-mcp-connection.md)

## 이런 상황에 사용합니다

- “Law MCP 연결해줘.”
- “법제처 인증코드를 등록하고 싶어.”
- `korean-law` 도구가 Codex에서 보이지 않거나 호출에 실패할 때
- 컴퓨터를 옮기거나 설정을 복구한 뒤 실제 법령 조회까지 검증할 때

## 무엇을 설정하나요?

1. 법제처 Open API `OC` 값의 허용 문자와 연결 가능성을 확인합니다.
2. 인증값을 Git 저장소가 아닌 로컬 자격증명 파일에 저장합니다.
3. Codex MCP 설정에 `korean-law` 서버를 등록합니다.
4. 기존 설정과 동명 스킬을 먼저 백업합니다.
5. Codex 재시작 후 읽기 전용 법령 질의로 실제 연결을 확인합니다.

## 설치

저장소 루트에서 다음을 실행하면 선택한 법률 스킬과 MCP를 함께 구성합니다.

```bash
python install.py --skills law-mcp-setup,biz-legal-team,biz-tax-team
```

MCP 설정만 필요하면:

```bash
python install.py --no-skills
```

설치기는 대화형으로 `OC` 값을 요청합니다. 값을 명령행 인자, README, `.env`, Git 커밋에 넣지 마세요.

## 요구사항

- Python 3.9 이상
- Node.js 20.19 이상
- `korean-law-mcp@4.8.0`
- 국가법령정보센터에서 발급받은 Open API `OC`

인증값이 없다면 [국가법령정보 공동활용](https://open.law.go.kr)에서 신청합니다. 이메일 비밀번호나 Codex 로그인 정보는 필요하지 않습니다.

## 저장과 보안

- 인증값은 사용자 로컬 credentials 파일에만 저장하고 권한을 제한합니다.
- 화면과 로그에는 전체 값을 다시 출력하지 않습니다.
- 기존 Codex 설정을 변경하기 전 백업을 확인합니다.
- API 거부를 우회하지 않으며 발급·승인 상태는 법제처에서 확인합니다.

## 완료 기준

- API 연결 시험과 인증값 형식 확인
- Codex 설정에 `korean-law` MCP 등록
- 앱 재시작 또는 새 작업 후 실제 도구 노출 확인
- “민법 제1조를 찾아줘” 같은 읽기 전용 질의 성공

설정 파일만 생성됐거나 버전 문자열만 확인된 상태는 완료로 보지 않습니다.

## 포함 파일

```text
law-mcp-setup/
├─ SKILL.md
├─ README.md
└─ agents/openai.yaml
```
