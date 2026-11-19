# nginx 보안 버전 확인

확인일: **2026-11-19**. 아래는 공지 중 두 취약점의 수정 기준이며 영구적인 안전 버전 목록이 아니다.
nginx 도입·업데이트 때 [공식 보안 공지](https://nginx.org/en/security_advisories.html)와
[변경 이력](https://nginx.org/en/CHANGES)을 다시 확인한다.

| 취약점 | upstream 영향 범위 | 해당 취약점 수정 버전 |
|---|---|---|
| CVE-2026-123007 · HTTP/2 flow control 메모리 손상 | 1.9.5–1.31.8 | stable 1.30.7+ / mainline 1.31.9+ |
| CVE-2026-123633 · HTTP/2 use-after-free | 1.19.7–1.31.8 | stable 1.30.7+ / mainline 1.31.9+ |

공식 변경 이력은 2026-11-18에 수정 사항을 발표했다. worker 권한과 서비스 노출도도 함께 평가한다.

- 운영 바이너리·컨테이너 digest·배포판 패키지 revision·활성 모듈을 대조한다.
- 배포판의 backport는 [해당 배포판 공지](https://ubuntu.com/security/cves)로 확인한다. upstream 숫자만으로 판정하지 않는다.
- NGINX Plus·Ingress controller·파생 제품은 각각 공급사 공지를 확인한다.
- 즉시 패치할 수 없으면 HTTP/2 노출 제한을 검토하되, 다른 취약점까지 해결했다고 판단하지 않는다.
- 패치 후 실제 실행 프로세스의 교체·연결·설정·rollback을 검증한다. 다운로드만으로 완료하지 않는다.

전체 스택의 재점검과 대응 기한은 [취약점 관리](vulnerability-management.md)를 따른다.
