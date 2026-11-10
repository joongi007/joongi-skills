# Usual Korean 조사 기록

확인 날짜: 2026-11-06. 아래는 원문을 복제한 것이 아니라 접근 방식에 대한 요약과 설계 판단이다.

| 자료 | 확인한 내용 | 반영한 판단 |
|---|---|---|
| [fluent-korean](https://github.com/snflkd/fluent-korean), [출력 지침](https://github.com/snflkd/fluent-korean/blob/main/plugins/fluent-korean/output-styles/fluent-korean.md) | 명확한 의미 전달을 중심에 둔 output style이며, 정착된 기술 용어와 원어를 구분한다. README는 MIT 라이선스를 안내한다. | 한국어 문장을 불완전하게 압축하지 않으며 제품 표기와 자연어 설명을 구분한다. |
| [im-not-ai](https://github.com/epoko77-ai/im-not-ai) | 한국어 번역체·상투적 문장을 검토하며 윤문 시 내용과 장르 보존을 강조한다. 저장소는 MIT 라이선스를 안내한다. | 구체적인 문맥에서 어색한 부분을 고치고 원문의 사실·조건·확신 수준을 보존한다. 정량 임계값이나 다단계 실행 체계는 가져오지 않는다. |
| [GeekNews 소개와 토론](https://news.hada.io/topic?id=32613) | fluent-korean 작성자가 명료성을 목표로 설명한다. 댓글에서는 비교 예제의 내용·형식까지 변하면 문체 개선을 판단하기 어렵다는 의견이 나온다. | 교정 전후에 의미가 유지되는 예제로 검토한다. 댓글을 언어 규칙이나 실험 결과로 취급하지 않는다. |

사용자는 영어의 기계적인 번역을 피하고 “SNS·팔로우·버튼”처럼 실제로 쓰는 표현을 선호한다.
이를 바탕으로 원어·음역·번역어 선택과 필요할 때의 웹 용례 조사를 독립적인 지침으로 작성했다.

구현: `skills/usual-korean/SKILL.md`와 두 참조 파일. 외부 스킬·스크립트·분류표를
복사하거나 설치하지 않았다. 한국어 스타일 지침의 적용은 클라이언트의 스킬 선택 동작에 의존하며,
output style 자동 설정이나 AI 판별 회피 성능을 제공한다고 주장하지 않는다.
