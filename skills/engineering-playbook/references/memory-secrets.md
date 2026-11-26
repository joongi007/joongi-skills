# 비밀의 메모리 수명·요청 컨텍스트 (PLAYBOOK §28)

목표는 평문 비밀의 복사·보관 시간과 진단 유출 경로를 줄이는 것이다.
**컨텍스트 정리는 메모리 즉시 삭제나 호스트 root 공격 방어를 보장하지 않는다.**
root·CAP_SYS_PTRACE·동등한 디버깅 권한은 실행 중 메모리를 관찰하거나 동작을 바꿀 수 있다.
디스크 암호화·OS 자격증명 저장소도 사용 순간의 평문을 완전히 숨기지는 못한다.
API key의 검증용 digest와 외부 호출용 복호화 가능한 비밀은 [API key 수명주기](api-key-security.md),
침해된 호스트 밖의 방어 경계는 [Zero Trust·서비스 간 통신](security-ops.md)을 본다.

## 요청·작업 종료 시 정리

- 요청의 비밀번호·토큰·복호화된 키를 불필요한 전역 cache·일반 세션 속성·로그 MDC·tracing baggage에 복사하지 않는다.
  BFF·OAuth client처럼 토큰 보관이 필요한 구성은 전용 저장 경계·암호화·최소 권한·만료·철회를 설계한다.
  의도적인 자격증명 보관과 요청 참조의 우발적 장기 보존을 구분한다.
  요청 객체나 인증 객체 전체를 background closure·예외·작업 이력에 오래 보관하지 않는다.
- 소유한 컨텍스트·stream·임시 buffer·callback 참조는 성공·실패·취소 모두 `finally`로 정리한다.
- Java의 사용자 정의 `ThreadLocal`은 pool thread를 반환하기 전에 `remove()`한다. 값만 null로
  바꾸는 것과 entry 제거를 구분한다. 라이브러리가 관리하는 SecurityContext는 해당 lifecycle을 따른다.
- async executor·CompletableFuture에서 컨텍스트를 넘길 때는 필요한 최소 값만 전달하고 작업 종료에
  복구·정리한다. Reactor Context는 subscriber 수명, Python contextvars는 reset token 수명으로 관리한다.
- 요청이 끝나도 작업이 살아 있다면 소유권·만료를 정의한다. 다른 진행 중 요청의 공유 컨텍스트를 지우지 않는다.

Java에서 **자신이 소유한 가변 배열**과 ThreadLocal을 사용하는 작은 예시:

```java
char[] password = readPassword();
try {
    requestSecrets.set(password); // 사용자 정의 ThreadLocal<char[]>
    usePassword(password);
} finally {
    java.util.Arrays.fill(password, '\0');
    requestSecrets.remove();
}
```

호출한 라이브러리의 복사본까지 지우는 코드는 아니다. 가능한 API에서는 `char[]`·`byte[]`,
`PBEKeySpec.clearPassword()` 등 명시적 정리를 사용한다. 불필요한 `new String(secret)`·Base64·JSON
직렬화는 복사본을 늘린다. Java String·Python str은 immutable이며 null·del·GC 요청이 덮어쓰기를
보장하지 않는다. JVM의 이동·복사·JIT·네이티브/TLS buffer 때문에 가변 배열 정리도 완전한 보장이 아니다.
`System.gc()`를 요청마다 호출하거나 런타임 내부 메모리를 임의로 덮어쓰지 않는다.

## 덤프·디버깅 경로 차단

- Actuator heapdump와 JVM attach·원격 JMX·디버거는 서로 다른 경로다. [Actuator 지침](java-actuator.md)을
  적용하고 운영에서 필요한 경로만 인증·네트워크 격리·시간 제한으로 연다.
- Linux `ulimit -c 0`·systemd `LimitCORE=0`만으로 모든 덤프를 막는다고 가정하지 않는다.
  `core_pattern`이 pipe collector로 연결되면 RLIMIT_CORE가 무시될 수 있다.
- systemd-coredump를 사용한다면 `Storage=none`과 `ProcessSizeMax=0` 등 collector 설정을 함께 검토한다.
  OS 전체 정책을 라이브러리 코드가 몰래 변경하지 않는다. 컨테이너·호스트별 실제 수집 경로를 확인한다.
- JVM의 `HeapDumpOnOutOfMemoryError`, `HeapDumpPath`, `jcmd`·attach·지원용 수집 작업은 OS core와
  별도로 검토한다. attach 차단은 운영 도구도 막을 수 있어 호환성 검사와 대체 관측 수단이 필요하다.
- 비특권 프로세스·capability 최소화·ptrace 제한·`PR_SET_DUMPABLE=0`은 방어층이다.
  특권 공격자에게 평문이 절대 보이지 않는다는 주장을 하지 않는다.
- 필요하면 KMS/HSM/별도 signer로 장기 개인키를 프로세스 밖에 두고 짧은 수명의 좁은 권한을 쓴다.
  공격자가 탈취한 작업 권한으로 signer를 호출할 가능성도 별도로 제한한다.

## 확인 방법

가짜 비밀만 사용해 pool thread 재사용·예외·취소·async 전파 후 컨텍스트가 남지 않는지 검사한다.
운영 데이터 없이 crash/heap dump 수집·보관·접근·삭제 경로를 확인한다. 로그·traces·cache·백업의
잔존도 함께 확인한다. 메모리 문자열 검색에서 안 보였다는 결과만으로 완전 삭제를 인증하지 않는다.

출처(2026-11-18): [Linux core](https://man7.org/linux/man-pages/man5/core.5.html),
[PR_SET_DUMPABLE](https://man7.org/linux/man-pages/man2/PR_SET_DUMPABLE.2const.html),
[systemd coredump.conf](https://www.freedesktop.org/software/systemd/man/latest/coredump.conf.html),
[Java PBEKeySpec](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/crypto/spec/PBEKeySpec.html).
