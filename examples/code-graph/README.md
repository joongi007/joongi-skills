# 코드 그래프 실사용 예제

설정 파일을 직접 편집하지 않고 실제 프로젝트를 Hub에 연결한다.

```bash
python3 scripts/check_code_graph.py --target .
python3 scripts/check_code_graph.py --target . --state-dir /tmp/joongi-hub-review --register
```

검토 Hub UI에서 `code-graph` 연결을 확인한다. `graph_status`로 freshness를 확인하고,
`graph_symbols`로 심볼을 찾은 뒤 `graph_callers`와 `graph_impact`를 호출한다.
소스를 바꾸면 `graph_index`를 먼저 실행한다.

이 예제는 임의 외부 패키지를 다운로드하지 않는 내장 Python AST 그래프를 사용한다.
외부 GitNexus 1.6.12를 실제로 설치·색인·Hub 연동한 기록은 [verification.json](verification.json),
선택 조건·라이선스·제한은 [운영 문서](../../docs/operations/01-code-graph.md)에 있다.
