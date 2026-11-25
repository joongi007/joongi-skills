# Spamhaus DROP와 네트워크 reputation 제어 (PLAYBOOK §24, §29)

Spamhaus DROP(Don't Route Or Peer)는 악성 운영자가 장악한 네트워크 범위 등을 거르는
threat-intelligence 기반 보조 방어다. 기존에 알려지지 않은 공격·정상 클라우드/감염 단말을 통한 공격은
남으므로 인증·인가·rate limit·WAF·egress 정책·DDoS 대응을 대체하지 않는다.
이 가이드는 도입 판단용이며 호스트 방화벽·BGP·클라우드 정책을 자동으로 바꾸라는 지시가 아니다.

## 피드와 이용 조건

| 공식 JSON 피드 | 의미 | 적용 시 구분 |
|---|---|---|
| `https://www.spamhaus.org/drop/drop_v4.json` | IPv4 CIDR 목록 | IPv4 packet/address family |
| `https://www.spamhaus.org/drop/drop_v6.json` | IPv6 CIDR 목록 | IPv6 우회·dual-stack 경로 확인 |
| `https://www.spamhaus.org/drop/asndrop.json` | ASN 목록 | ASN은 CIDR이 아님. 라우팅 정책·별도 매핑 검증 필요 |

공식 안내는 JSON을 권장한다. 과거 eDROP은 DROP에 통합되었으므로 별개 최신 피드로 가정하지 않는다.
DROP의 무료 이용 조건과 출처·날짜·저작권 표시 보존을 확인한다. 다른 Spamhaus DNSBL/DQS나
상용 BGP 피드의 이용 조건을 DROP과 동일하게 해석하지 않는다.
피드 파일을 앱 배포물·Git에 무기한 박제하지 않고 업데이트 가능한 운영 데이터로 관리한다.

## 집행 위치와 신뢰할 IP

경계 gateway·방화벽·egress 계층 등 실제 패킷을 관측하는 위치와 ingress/egress 적용 범위를 정한다.
CDN·reverse proxy 뒤의 origin firewall은 대개 proxy IP만 본다. 신뢰한 proxy의 검증된 client IP를
이용하는 edge/app 정책과 네트워크 source IP 정책을 구분한다. 임의 X-Forwarded-For를 믿지 않는다.
허용 CDN을 차단하지 않으려고 origin을 전체 인터넷에 여는 식의 우회도 피한다.
발신지/목적지 차단이 NAT·관리 접근·DNS·인증·백업·모니터링에 미칠 영향을 확인한다.

대용량 DDoS가 upstream 회선을 포화시키면 앱·로컬 방화벽의 DROP만으로 회복되지 않는다.
상위 공급자의 filtering/scrubbing·용량·연락 절차를 별도로 준비한다.

## 안전한 갱신과 적용

1. 담당자·갱신 주기·최대 stale 시간·영향 범위를 정한다. 공식 안내에 맞춰 일 단위 fetch부터 검토하고,
   자동 다운로드 간격은 최소 1시간 이상 둔다. 실패 재시도·복제본도 같은 제한을 공유한다.
   요청마다 조회하지 말고 한 곳에서 수집해 내부 검증 사본을 배포하는 방식을 고려한다.
2. HTTPS 공식 출처에서 timeout·크기 상한을 두고 임시 파일로 받는다. 응답 상태·형식·필요한 metadata·
   CIDR/ASN 범위·건수·전후 변화량을 검증한다. metadata record와 실제 차단 항목을 구분하고,
   빈 응답·HTML 오류·`0.0.0.0/0`·`::/0`·비정상 대량 변화를 정상 업데이트로 수용하지 않는다.
3. updater의 네트워크·파일 권한과 정책 적용 계정의 특권을 분리한다. 피드 문자열을 shell 명령으로
   해석하지 않는다. 플랫폼의 검증·transaction/set 교체 기능으로 전용 규칙만 원자적으로 교체한다.
   전체 firewall flush나 파일을 읽는 도중의 부분 적용을 하지 않는다.
4. 실패 시 마지막 검증 사본을 제한된 기간 유지하고 freshness·다운로드/파싱/적용 실패를 알린다.
   오래된 사본을 영구 유지하거나 실패를 빈 목록으로 덮어쓰지 않는다. 최대 stale 초과 시 유지/제거/제한 중
   선택할 정책·담당자·승인·복구를 사전에 정한다. 불특정 전체 인터넷을 자동 차단하지 않는다.
5. monitor-only·canary 후 단계적으로 집행하고 이전 검증 버전으로 rollback할 경로와 별도 관리 접속을 둔다.
   allowlist 예외는 최소 범위·사유·소유자·만료·감사를 갖춘다. 전체 ASN·공유 proxy를 광범위하게 예외 처리하지 않는다.

## 검증과 관측

합성 fixture로 IPv4/IPv6 매칭·비매칭, proxy IP 위조, 피드 오류·과대 응답·빈 목록·잘못된 prefix,
권한 실패·동시 updater·재시작·stale 초과·목록에서 제거된 범위의 해제·canary/rollback을 확인한다.
block 수뿐 아니라 정상 요청 실패·egress 영향·feed age·차단/예외 rule 버전과 적용 시간을 기록한다.
전체 차단 패킷의 무제한 로그로 디스크를 소진시키지 않는다. 반영되지 않은 노드·기존 연결도 확인한다.

관련: [Zero Trust·egress](security-ops.md), [탐지·차단·복구](incident-response.md), [공개 API](api-key-security.md).
공식 자료 확인: 2026-11-25.
[DROP 안내·이용 조건](https://www.spamhaus.org/blocklists/do-not-route-or-peer/),
[FAQ·갱신 간격](https://www.spamhaus.org/faqs/do-not-route-or-peer-drop/),
[Fair Use Policy](https://www.spamhaus.org/blocklists/drop-fair-use-policy/),
[DROP/eDROP 통합 공지](https://www.spamhaus.org/resource-hub/network-security/spamhaus-drop-and-edrop-to-become-a-single-list/).
검증·원자적 적용·오탐 대응 절차는 운영 권고이며 공급자의 모든 요구를 대신하는 약관 요약은 아니다.
