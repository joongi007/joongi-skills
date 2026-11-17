# Spring Boot Actuator 보안 (PLAYBOOK §28)

Actuator의 heapdump 노출은 root 권한 없이도 JVM 메모리 자료를 유출할 수 있다.
관리 endpoint 인증·네트워크 격리와 [메모리·컨텍스트 수명](memory-secrets.md)을 함께 검토한다.

## 노출과 권한을 별도로 제한

- 운영은 endpoint 허용 목록으로 시작한다. `include: "*"`를 기본으로 쓰지 않는다.
- `health`의 상세·컴포넌트 정보는 공개하지 않는다. `prometheus`는 내부 수집기가 필요할 때만 추가한다.
- `heapdump`, `env`, `configprops`, `logfile`, `loggers`, `threaddump`, `mappings`, `shutdown` 등은
  진단 자료·토큰·구조 노출이나 운영 상태 변경 가능성을 따져 기본 차단한다. GET·read-only도 안전하다는 뜻은 아니다.
- HTTP와 JMX를 각각 검토한다. HTTP 차단만으로 원격 JMX·JVM attach 경로가 닫히지는 않는다.
- 별도 포트·경로 변경은 인증을 대체하지 않는다. Ingress·방화벽·NetworkPolicy에서 관리 포트를
  제한하고 인터넷·사용자용 reverse proxy에 우연히 노출되지 않는지 확인한다.

Spring Boot **3.4+·4.x에서 지원하는 access 설정**의 최소 예시다. 사용하는 버전의 공식
configuration metadata로 키를 확인한다. 이전 버전에 그대로 붙여 넣지 않는다.

```yaml
spring:
  jmx:
    enabled: false
management:
  endpoints:
    access:
      default: none
    web:
      exposure:
        include: health
    jmx:
      exposure:
        exclude: "*"
  endpoint:
    health:
      access: read-only
      show-details: never
      show-components: never
    heapdump:
      access: none
    env:
      show-values: never
    configprops:
      show-values: never
```

`management.server.port`를 따로 두면 외부 서비스 포트와 관리 포트의 라우팅을 분리할 수 있다.
`management.server.address: 127.0.0.1`은 **별도 관리 포트를 사용하며 로컬 probe·수집기만 접근할 때**
선택한다. 다른 Pod의 수집기·kubelet probe가 필요한 환경에는 그대로 적용하지 않는다.

## Spring Security 주의사항

- custom `SecurityFilterChain`을 정의하면 Boot의 Actuator 보안 자동 설정이 물러난다.
  애플리케이션 경로뿐 아니라 Actuator 경로도 명시적으로 보호한다.
- 관리용 chain은 `EndpointRequest.toAnyEndpoint()`로 실제 endpoint를 매칭하고, 허용한 health
  이외에는 운영자 역할·인증된 수집기만 허용한다. 별도의 application catch-all chain도 빠뜨리지 않는다.
- Boot 3.x·4.x에서 `EndpointRequest` 패키지 위치가 다르므로 해당 버전 예제를 확인한다.
- 단순히 Actuator를 쓰려고 전역 CSRF를 끄지 않는다. 필요한 비브라우저 관리 API에 한정해 결정한다.
- Basic·Bearer 자격증명은 TLS·네트워크 격리와 함께 사용하고, 모니터링 계정에 사용자 API 권한까지 주지 않는다.
- `show-values` 마스킹은 heapdump·로그·사용자 정의 endpoint의 민감정보까지 정리해주지 않는다.

## 수용 검사

실제 운영 profile·custom chain·Ingress를 켠 환경에서 다음을 확인한다.

1. 미인증 `/actuator/health`는 최소 상태만 보여주고 상세·컴포넌트·민감 속성은 없다.
2. `heapdump`, `env`, `configprops`, `shutdown`은 구성에 따라 404·401·403 등으로 차단된다.
   경로만 검사하지 말고 실제 응답에 진단 데이터가 없는지도 본다.
3. 일반 사용자·수집기·운영자 권한을 구분하고 관리 쓰기 요청을 검사한다.
4. 관리 포트가 외부 Ingress·LoadBalancer에 연결되지 않았고 원격 JMX도 차단됐는지 확인한다.
5. 긴급 덤프를 허용했다면 만료·접근 감사·암호화 보관·삭제를 적용하고, 유출 시 키를 교체한다.

출처(2026-11-18): [Spring Boot 3.5 endpoints](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html),
[Spring Boot 3.4 endpoints](https://docs.spring.io/spring-boot/3.4/reference/actuator/endpoints.html),
[Spring Boot 현재 endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html).
