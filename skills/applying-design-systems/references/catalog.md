# 카탈로그 — open-design `design-systems/` 슬러그

## 목차

- 이 목록에 대하여
- 라이브 조회 (권장)
- 스냅샷 (2026-09-05)
- 슬러그가 없을 때

## 이 목록에 대하여

`github.com/nexu-io/open-design` 의 `design-systems/` 하위 디렉터리 이름 = 슬러그.
슬러그가 곧 URL 경로다.

```
https://raw.githubusercontent.com/nexu-io/open-design/main/design-systems/<slug>/tokens.css
```

**저장소는 계속 늘어난다.** README는 151개라고 하는데 2026-09-05에 contents API로 센
디렉터리는 229개였다. 아래 스냅샷은 그날 확인한 것이고, **완전한 목록이 아니다** —
API 응답이 알파벳순 `totality-festival` 근처에서 잘렸다. 그 뒤(u~z)는 여기 없다.

## 라이브 조회 (권장)

목록이 필요하면 스냅샷을 믿지 말고 직접 조회한다.

```bash
curl -s https://api.github.com/repos/nexu-io/open-design/contents/design-systems \
  | grep '"name"' | cut -d'"' -f4
```

웹 조회 도구만 있으면 같은 URL을 열면 된다.
브라우저로 볼 때는 https://github.com/nexu-io/open-design/tree/main/design-systems

## 스냅샷 (2026-09-05)

229개 중 확인된 135개. `_schema` 는 슬러그가 아니라 스키마 디렉터리다.

### 제품·SaaS
`agentic` `airtable` `application` `arc` `cal` `composio` `expo` `figma` `framer` `intercom`
`kami` `levels` `lingo` `linear-app` `loom` `lovable` `miro` `notion` `slack` `superhuman`

### 개발자 도구·인프라
`clickhouse` `cloudflare-kumo` `cursor` `github` `hashicorp` `mongodb` `opencode-ai` `posthog`
`raycast` `replicate` `resend` `sanity` `sentry` `shadcn` `stripe` `supabase`

### AI
`claude` `cohere` `elevenlabs` `huggingface` `minimax` `mistral-ai` `ollama` `openai`
`perplexity` `runwayml` `together-ai`

### 커머스·핀테크
`binance` `coinbase` `kraken` `mastercard` `revolut` `shopify`

### 컨슈머 브랜드
`airbnb` `apple` `canva` `discord` `duolingo` `meta` `nike` `nvidia` `pinterest` `playstation`
`spacex` `spotify` `starbucks` `tesla`

### 자동차
`bmw` `bmw-m` `bugatti` `ferrari` `lamborghini` `renault`

### 엔터프라이즈·시스템
`ant` `cisco` `corporate` `enterprise` `ibm` `material` `professional`

### 레이아웃 성격
`bento` `dashboard` `hud` `mission-control` `perspective` `publication` `theverge` `mintlify`

### 순수 스타일 (브랜드 아님)
`artistic` `atelier-zero` `bold` `brutalism` `cafe` `clay` `claymorphism` `clean` `colorful`
`contemporary` `cosmic` `creative` `dithered` `doodle` `dramatic` `editorial` `elegant`
`energetic` `expressive` `fantasy` `flat` `friendly` `futuristic` `glassmorphism` `gradient`
`luxury` `minimal` `modern` `mono` `neobrutalism` `neon` `neumorphism` `pacman` `paper`
`premium` `refined` `retro` `simple` `skeumorphism` `sleek` `spacious` `storytelling`
`tetris` `tom-modern` `totality-festival`

### 중립 기본값
`default` `clean` `modern` `simple`

## 슬러그가 없을 때

- **404가 나면** 슬러그가 틀렸거나 그 사이 이름이 바뀐 것이다. 라이브 조회로 확인한다.
- **원하는 브랜드가 없으면** 만들어내지 말고, 성격이 가장 가까운 스타일 슬러그
  (`luxury`, `editorial`, `minimal` 등)를 쓰고 그렇게 선택했다고 말한다.
- 브랜드 슬러그는 **그 브랜드에서 영감을 받은 것**이지 공식 자산이 아니다
  (`DESIGN.md` 제목이 "Design System Inspired by Linear" 형태다).
  실제 브랜드를 사칭하는 결과물에 쓰지 않는다.
