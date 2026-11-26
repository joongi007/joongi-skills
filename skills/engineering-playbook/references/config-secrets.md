# 설정·비밀 주입과 연결 URL (PLAYBOOK §15)

설정(configuration)과 비밀(secret)을 구분한다. 설정의 기본값·필수값·형식·출처·우선순위·갱신 시점을
정의하고 시작 시 검증한다. 필드명·prefix는 기존 프로젝트 계약을 유지한다.

## 비밀의 저장·주입·수명

- 원문 비밀을 코드·Git·이미지 레이어·빌드 인자·공개 문서에 넣지 않는다.
- 환경변수는 주입 수단 중 하나다. OS credential store·secret manager·KMS·권한 제한 파일/mount 등을
  배포 환경에 맞춰 선택한다. 환경변수도 자식 프로세스·진단·덤프에 노출될 수 있다.
- 로컬 `.env`를 쓰면 Git에서 제외하고 파일 권한·백업·공유 범위를 제한한다. `.env.example`에는
  키와 가짜 값·설명을 둔다. `.env`에만 실제 비밀을 보관해야 한다는 규칙은 없다.
- Vite의 `VITE_*`처럼 브라우저 번들에 포함되는 값에는 비밀을 넣지 않는다.
- 필요한 서비스에 필요한 자격만 주입한다. prefix는 이름 충돌을 줄일 뿐 접근 통제는 아니다.
- 회전 시 reload·재기동·연결 풀 교체와 기존 자격 폐기를 검증한다. 전역 settings나 URL cache를
  무기한 유지하면 새 비밀이 반영되지 않을 수 있다. 복호화 사본 수·수명은 [메모리 지침](memory-secrets.md)을 따른다.
- 오류·로그·repr·설정 출력에 비밀이 포함되지 않게 한다. 마스킹 타입도 사용 순간의 평문을 없애지는 않는다.

## URL 구성요소 인코딩 (§15)

드라이버의 URL builder·명시적 연결 파라미터를 우선한다. SQLAlchemy 예시:

```python
from sqlalchemy import URL

url = URL.create(
    "postgresql+asyncpg",
    username=user,
    password=password,  # 원문 구성요소; 미리 percent-encode하지 않는다
    host=host,
    port=port,
    database=database,
)
engine = create_async_engine(url)
```

문자열 URL이 필요한 경우 userinfo·path·query마다 해당 드라이버의 decoding 규칙에 맞춰 인코딩한다.
`quote_plus`는 form/query의 공백을 `+`로 바꾸므로 모든 드라이버의 password 구성요소에
일괄 적용하지 않는다. percent-encoding이 필요한 userinfo에는 `quote(value, safe="")` 같은 방식을
드라이버 계약과 대조한다. 전체 URL 인코딩·이중 인코딩을 피하고 공백·`+`·`@`·`/`·Unicode를 회귀 검사한다.

## pydantic-settings 선택형 예시

Python에서 `BaseSettings`를 사용할 수 있다. `env_prefix="API_"` 같은 prefix는 팀 명명 규칙이며
모든 프로젝트의 필수값이 아니다. `.env` 보간은 읽는 도구의 지원·우선순위를 검증한다.
`cached_property`는 성능 선택지다. 비밀 포함 URL을 cache하면 재설정·회전·노출·수명 비용을 함께 검토한다.
`Field(description=...)`에는 필드 의미·단위·허용값을 쓰고 실제 자격증명을 넣지 않는다.

관련: [Compose 주입](docker.md), [API key 수명주기](api-key-security.md), [운영 비밀](security-ops.md).
근거(2026-11-27): [SQLAlchemy URL.create·escaping](https://docs.sqlalchemy.org/en/20/core/engines.html).
