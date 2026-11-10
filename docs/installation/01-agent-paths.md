# 에이전트 설치 경로와 MCP 등록

검증일: 2026-11-05. 에이전트는 `SKILL.md`를 읽는 디렉터리와 MCP 설정 형식이 서로 다르다.
현재 버전에서 지원하는 범위를 아래 표로 관리한다.

<!-- contract: agents.skills = {"claude":".claude/skills","codex":".agents/skills","cursor":".cursor/skills","copilot":".copilot/skills","gemini":".gemini/skills","opencode":".config/opencode/skills"} -->

| 에이전트 | 자동 탐지 경로 | 설치 스킬 경로 | Hub MCP 등록 |
|---|---|---|---|
| Claude Code | `~/.claude/` | `~/.claude/skills/` | `~/.claude.json`, `mcpServers.joongi-hub` |
| Codex | `~/.codex/` | `~/.agents/skills/` | `~/.codex/config.toml`, `mcp_servers."joongi-hub"` |
| Cursor | `~/.cursor/` | `~/.cursor/skills/` | `~/.cursor/mcp.json`, `mcpServers.joongi-hub` |
| Gemini CLI | `~/.gemini/` | `~/.gemini/skills/` | `~/.gemini/settings.json`, `mcpServers.joongi-hub` |
| GitHub Copilot CLI | `~/.copilot/` | `~/.copilot/skills/` | `~/.copilot/mcp-config.json`, `mcpServers.joongi-hub` |
| OpenCode | `~/.config/opencode/` | `~/.config/opencode/skills/` | `~/.config/opencode/opencode.json(c)`, `mcp.joongi-hub` |

경로 탐지는 설치 여부의 휴리스틱이다. 실행 파일을 호출하거나 인증 상태를 읽지 않는다.
설정 경로를 바꾼 사용자는 `--agent`와 `--home`으로 명시적으로 설치하거나 직접 연결한다.
`CODEX_HOME`, XDG 경로 재정의, 에이전트별 커스텀 프로필 경로는 현재 자동 추적하지 않는다.

Codex의 현재 공유 경로는 `~/.agents/skills`이다. 과거의 `~/.codex/skills`에 설치된
파일은 이 설치기가 가져오거나 삭제하지 않는다. Cursor·Gemini·OpenCode도 공유 경로의
스킬을 발견할 수 있으므로 에이전트 간 같은 이름의 우선순위를 확인한다.

JSON 설정은 `mcpServers.joongi-hub` 항목만 관리하고 다른 항목은 유지한다. Copilot은
`type: local`, `tools: ["*"]`를 함께 등록한다. 일반 JSON 공백·들여쓰기는 정규화된다.
OpenCode는 `mcp.joongi-hub`에 `type: local`, `command: [런처, "stdio"]`, `enabled: true`를 등록한다.
기존 `opencode.jsonc`가 있으면 그 파일을 선택하며 주석·trailing comma·관련 없는 설정의 원문을 보존한다.
JSON·JSONC가 함께 있으면 높은 우선순위의 JSONC에 등록하고 다른 파일의 같은 이름 충돌을 검사한다.
중복 키나 잘못된 구조는 추측하지 않고 중단한다. 다른 에이전트의 설정은 표준 JSON만 지원한다.
Codex TOML에는 명확한 시작·끝 주석이 있는 별도 테이블을 추가한다.
사용자가 관리 항목을 수정했다면 업데이트·제거 시 그 항목을 덮어쓰지 않는다.

## 수동 MCP 연결

stdio 실행 명령은 POSIX에서 `~/.local/bin/joongi-hub stdio`이다.
Windows에서는 설치기가 만든 `.cmd` 런처를 사용한다.

```json
{
  "mcpServers": {
    "joongi-hub": {
      "command": "/absolute/home/.local/bin/joongi-hub",
      "args": ["stdio"]
    }
  }
}
```

경로의 `/absolute/home`은 실제 홈으로 바꾼다. JSON 설정은 일반적으로 `~`를 셸처럼
확장하지 않는다. 여러 클라이언트가 같은 Hub 상태를 읽을 수 있지만 변경은 Hub의 상태
저장소 규칙을 따른다.

## 실제 CLI 확인

2026-11-05에 Codex CLI 0.166.0과 Claude Code 2.1.233을 임시 홈에서 실행했다.
Codex의 `mcp list --json`·`mcp get joongi-hub --json`이 설치한 활성 stdio 설정과
절대 런처 경로·인자를 인식했다. Claude의 `mcp get joongi-hub`는 User config scope와
Connected 상태를 반환하여 실제 로컬 Hub 연결까지 확인했다.
이 검증은 인증·모델 호출을 사용하지 않으며 스킬 자동 활성화나 Apps 렌더러 검증과는 구분한다.

```bash
python3 tests/agent_cli_smoke.py --codex /path/to/codex --claude /path/to/claude
```

공식 문서의 `CODEX_HOME`, `CLAUDE_CONFIG_DIR`와 별도 HOME/XDG/state 경로를 사용해
실제 사용자 설정·인증 파일을 읽지 않는다. Codex는 임시 디렉터리에 helper alias를 만들지
않는다는 경고를 출력할 수 있으나 두 조회 명령은 정상 종료했다.

## 공식 출처

- [Claude Code skills](https://code.claude.com/docs/en/skills)
- [Claude Code MCP configuration](https://code.claude.com/docs/en/mcp)
- [Codex skills, official OpenAI documentation](https://learn.chatgpt.com/docs/build-skills)
- [Codex MCP configuration](https://developers.openai.com/codex/mcp)
- [Cursor skills](https://cursor.com/docs/skills)
- [Cursor MCP](https://cursor.com/docs/context/mcp)
- [Gemini CLI skills](https://geminicli.com/docs/cli/skills/)
- [Gemini CLI MCP servers](https://geminicli.com/docs/tools/mcp-server/)
- [Copilot personal skills](https://learn.microsoft.com/en-us/visualstudio/ide/copilot-agent-skills)
- [Copilot CLI MCP registration](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-mcp-servers)
- [OpenCode MCP servers](https://opencode.ai/docs/mcp-servers/)
- [OpenCode configuration and JSONC](https://opencode.ai/docs/config/)
- [OpenCode skills](https://opencode.ai/docs/skills/)
