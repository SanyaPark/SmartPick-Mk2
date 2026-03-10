# SmartPick 프론트엔드 (SmartPick Frontend)

SmartPick 프론트엔드는 Next.js 14, React 18, TailwindCSS 및 TypeScript로 구축된 고성능 신용카드 컨시어지 서비스입니다. 3D 오빗(Orbit) 경험과 AI 스타일의 채팅 인터페이스를 결합하여 사용자에게 맞춤형 카드를 추천합니다.

## 기술 스택 (Tech Stack)

- **Framework:** Next.js 14 (Pages Router)
- **Library:** React 18
- **Styling:** TailwindCSS (커스텀 테마 토큰 포함)
- **Language:** TypeScript
- **AI Integration:** `@openai/chatkit-react` (Mocked fetch 핸들러 사용)

## 사전 요구 사항 (Prerequisites)

- **Node.js:** 18.17 이상 (Next.js 14 요구 사항)
- **npm:** 9 이상 (권장)

## 시작하기 (Getting Started)

1. **의존성 설치:**
   ```bash
   npm install
   ```

2. **개발 서버 실행:**
   ```bash
   npm run dev
   ```
   브라우저에서 [http://localhost:3000](http://localhost:3000)을 열어 결과를 확인하세요.

## 사용 가능한 스크립트 (Available Scripts)

| 명령어 | 설명 |
| :--- | :--- |
| `npm run dev` | 핫 리로딩을 지원하는 Next.js 개발 서버를 시작합니다. |
| `npm run build` | 프로덕션을 위한 최적화된 빌드를 생성합니다. |
| `npm run start` | 빌드된 프로덕션 서버를 실행합니다 (`build` 선행 필요). |
| `npm run lint` | 정적 분석을 위해 ESLint를 실행합니다. |

## 프로젝트 구조 (Project Structure)

```text
apps/frontend/
├── components/        # LumenOrbitCarousel, CardCarousel, ChatKitWrapper 등
├── pages/             # _app.tsx, _document.tsx, index.tsx, recommend.tsx
├── public/            # 공개 리소스
├── styles/            # tailwind로 이루어진 globals.css
├── tailwind.config.js # 테마 확장 (customTeal/customNavy/customGreen)
└── tsconfig.json      # TypeScript 컴파일러 옵션
```

### 환경 설정 및 구성 (Environment & Config)

- .env 필요없음. ChatKit 호출은 로컬에서 가로채어 처리됩니다.
- Tailwind는 클래스 사용 여부를 확인하기 위해 `pages/`, `components/`, `app/` 디렉토리를 스캔합니다.

## 핵심 UI 컴포넌트 (Core UI Components)

### `LumenOrbitCarousel`
포인터 드래그/기울기에 반응하는 CSS 기반 3D 오빗 컴포넌트입니다. 회전하는 오빗에 기능 카드를 표시하여 시각적 효과를 제공합니다.
- **출처:** 이 컴포넌트는 [ReactVerse](https://reactverse.dev/components/lumen-orbit-carousel)의 소스를 기반으로 제작됨.

### `CardCarousel`
`framer-motion`을 사용한 실제 신용카드 3D 카루셀입니다.
- **커스터마이징:** 카드는 `components/CardCarousel.tsx` 내의 `CARDS` 배열에 정의되어 있습니다. 이 데이터를 수정하여 카드 옵션, 그라데이션 또는 메타데이터를 추가/삭제할 수 있습니다.

### `ChatKitWrapper`
`@openai/chatkit-react`를 감싸고 OpenAI 응답을 시뮬레이션하는 `mockFetch`를 주입합니다. 사용자의 메시지를 분석하여 적절한 카드를 선택하고 `onSpin`/`onCardSelected` 콜백을 트리거하여 Carousel이 추천 카드를 강조하도록 합니다.
- **중요:** 이 컴포넌트는 로컬에서 API 호출을 간섭하며, **실제 OpenAI API와 통신하지 않습니다.** 향후에 Upstage API를 연결할것입니다.

## 스타일링 및 테마 (Styling & Theme)

`tailwind.config.js`에서 브랜드 고유의 색상을 확장하여 사용합니다:
- **customTeal:** `#4ac0a7` (브랜드 글로우)
- **customNavy:** `#1f244a` (배경색)
- **customGreen:** `#7cb45b` (강조색)

`styles/globals.css`는 루트 배경/전경 변수를 설정하고, Tailwind 레이어를 가져오며, 채팅창 스크롤바 숨김과 같은 공통 유틸리티를 제공합니다.

## 테스트 및 품질 관리 (Testing & Quality)

- 커밋 전 코드 일관성을 위해 `npm run lint`를 실행하세요.
- 프로덕션 번들이 오류 없이 컴파일되는지 확인하기 위해 `npm run build`를 실행하세요.
