---
name: law-mcp-setup
description: Connect or repair Korean Law MCP in Codex by collecting the user's National Law Information Center Open API OC authentication value, checking its format and API connectivity, storing it locally, and registering the MCP safely. Use when the user says "Law MCP 연결해줘", "법제처 인증코드 등록", "인증코드 입력해서 연동", "korean-law MCP가 안 돼", or asks to install, reconnect, diagnose, or verify the Korean law MCP.
---

# Law MCP 연결

법제처 국가법령정보센터 Open API의 `OC` 인증값을 받아 Korean Law MCP를 Codex에 연결한다.

## 연결 절차

1. 사용자가 이 대화에서 `OC` 값을 제공하지 않았다면 다음 문장으로 한 번만 묻는다.

   `당신의 인증 코드는 무엇인가요?`

2. 사용자가 입력한 값을 임의로 보정하지 않는다. 영문자·숫자·점·밑줄·하이픈만 허용한다.
3. 설치 스크립트를 다음 순서로 찾는다.

   - 이 스킬의 `SKILL.md`에서 두 단계 위에 있는 플러그인 루트의 `scripts/setup.py`
   - `${CODEX_HOME:-~/.codex}/biz-law-codex/scripts/setup.py`

4. 설치 스크립트를 TTY 대화형 모드로 실행하고 프롬프트가 뜨면 사용자가 제공한 `OC`를 표준입력으로 전달한다.

   ```bash
   python3 /확인한/경로/setup.py
   ```

   두 번째 런타임 경로를 사용한다면 이미 설치된 스킬을 건드리지 않도록 `--no-skills`를 붙인다.

5. 성공 메시지에서 아래 세 항목을 확인한다.

   - 법제처 API 연결 시험과 OC 형식 확인
   - `korean-law` MCP 설정 등록
   - Biz 스킬 설치

6. Codex 앱을 다시 시작하거나 새 작업을 열어 MCP를 다시 로드하도록 안내한다.
7. 재시작 뒤 `민법 제1조를 찾아줘` 같은 읽기 전용 질의로 최종 확인한다.

## 보안 규칙

- 인증값을 저장소 파일, README, 예제, 커밋, 로그에 기록하지 않는다.
- 채팅 답변이나 명령 출력에 인증값 전체를 다시 표시하지 않는다.
- 설치기는 값을 `${CODEX_HOME:-~/.codex}/biz-law-codex/credentials.json`에 권한 `0600`으로 저장한다.
- 기존 Codex 설정을 바꾸기 전에 자동 백업이 생성됐는지 확인한다.
- 법제처가 요청을 거부한 경우 이를 우회하지 않는다. 네트워크 장애만 발생한 경우에는 설치기의 경고를 그대로 전달한다.
- 기본 검색 API 응답만으로는 `OC`의 발급·소유 여부를 판정할 수 없음을 숨기지 않는다. 필요하면 법제처 마이페이지에서 확인하도록 안내한다.

## 인증값이 없는 경우

법제처 [국가법령정보 공동활용](https://open.law.go.kr)에서 Open API 사용을 신청하고 발급된 `OC` 인증값을 확인하도록 안내한다. 이메일 비밀번호나 Codex 로그인 정보는 받지 않는다.
