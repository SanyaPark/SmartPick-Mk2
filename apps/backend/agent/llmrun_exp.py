"""
[실험용] LLM 기반 카드 필터링 & 랭킹 로직

기존 llmrun.py의 코드 기반 filter → score → calculate 파이프라인을
LLM 판단으로 대체하여 성능을 비교합니다.

흐름: 유저 입력 → LLM 필터링/스코어링 → 코드 계산 → LLM 설명
기존 llmrun.py에 전혀 영향을 주지 않는 독립 모듈입니다.
"""

import os
import json
import time
import uuid

from datetime import datetime
from pathlib import Path
from typing import Annotated, Dict, List, Literal, Optional
from typing_extensions import NotRequired, TypedDict

from dotenv import load_dotenv

from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import InMemorySaver
from langchain.chat_models import init_chat_model
from langchain_core.messages import SystemMessage, AIMessage, AnyMessage
from langchain_core.runnables import RunnableConfig
from langsmith import traceable
from langfuse import observe, Langfuse

from apps.backend.agent.prompts import EXPLAIN_PROMPT, QA_PROMPT

# ===========================< Setting >============================
load_dotenv(Path(__file__).resolve().parents[3] / ".env")

os.environ["LANGSMITH_TRACING_V2"] = "true"
os.environ["LANGSMITH_PROJECT"] = "Smart_Pick_Exp"
os.environ["LANGSMITH_ENDPOINT"] = "https://api.smith.langchain.com"

langfuse = Langfuse()

MODEL = "solar-pro2"
llm = init_chat_model(model=MODEL, temperature=0.0)

# ===========================< Test Log >============================
TEST_LOG_DIR = Path(__file__).resolve().parents[3] / "test_logs" / "exp"
PROMPT_VERSIONS = {"LLM_FILTER": "V1", "EXPLAIN_PROMPT": "V3", "QA_PROMPT": "V1"}

_test_log: dict = {}


def _init_test_log(total_budget: int, category_spending: dict):
    global _test_log
    _test_log = {
        "timestamp": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "model": MODEL,
        "prompt_versions": PROMPT_VERSIONS,
        "experiment": "llm_filter_ranking",
        "input": {
            "total_budget": total_budget,
            "category_spending": category_spending,
        },
        "llm_filter_result": {},
        "calc_results": [],
        "top3": [],
        "explain_raw": "",
    }


def _save_test_log(case_name: str):
    TEST_LOG_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = case_name.replace(" ", "_").replace("+", "")
    filepath = TEST_LOG_DIR / f"{ts}_{safe_name}.json"
    filepath.write_text(json.dumps(_test_log, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[LOG] 실험 로그 저장: {filepath}")


# ===========================< Data Loading >============================
# llmrun.py와 동일한 데이터 로딩 로직 재사용

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATASETS_DIR = PROJECT_ROOT / "datasets" / "json_v2"
DIGEST_DIR = PROJECT_ROOT / "datasets" / "digest"


def load_all_cards() -> list[dict]:
    all_cards = []
    for company_dir in DATASETS_DIR.iterdir():
        if not company_dir.is_dir():
            continue
        for json_file in company_dir.glob("*.json"):
            data = json.loads(json_file.read_text(encoding="utf-8"))
            if not data.get("card_name"):
                continue
            digest_path = DIGEST_DIR / company_dir.name / f"{json_file.stem}.md"
            data["_digest_path"] = str(digest_path)
            data["_file_stem"] = json_file.stem
            all_cards.append(data)
    return all_cards


def load_digest(card: dict) -> str:
    digest_path = Path(card.get("_digest_path", ""))
    if digest_path.exists():
        return digest_path.read_text(encoding="utf-8")
    return f"# {card.get('card_name', '알 수 없음')}\n(digest 파일 없음)"


# ===========================< LLM Filter Prompt >============================

LLM_CALC_PROMPT_V1 = """
너는 신용카드 혜택 계산 분석가다.

[유저 소비 패턴]
월 총 소비: {total_budget:,}원
카테고리별 소비:
{spending_lines}

[카드 혜택 원본 데이터]
{card_digest}

[카드 구조화 데이터]
{card_json}

[작업]
위 카드의 혜택 정보를 분석하고, 유저 소비 패턴에 맞는 월 예상 할인/적립 금액을 계산해줘.

[분석 & 계산 규칙]
1. 먼저 혜택 유형을 파악하라:
   - 정률 할인 (예: 5% 할인) → 소비금액 × 할인율
   - 정액 할인 (예: 건당 300원) → 예상 이용 횟수 × 할인금액
   - 포인트 적립 (예: 1,000원당 10P) → 소비금액 ÷ 기준금액 × 적립포인트
   - 캐시백 (예: 월 5,000원) → 조건 충족 시 고정 금액
2. 월 한도가 있으면 반드시 적용하라. 계산 결과가 한도를 초과하면 한도까지만 인정.
3. 전월실적 구간에 따라 혜택이 달라지면, 유저의 월 총 소비({total_budget:,}원)에 해당하는 구간을 적용하라.
4. 유저 소비 카테고리와 무관한 혜택은 계산하지 말 것.
5. 데이터에 명확한 수치가 없는 혜택은 "unclear"로 분류하고 0원 처리.
6. 계산 과정(reasoning)을 반드시 포함하라. 어떤 근거로 어떤 공식을 적용했는지 기록.

[출력 형식] 반드시 아래 JSON 포맷만 출력하세요. 마크다운이나 설명 없이 JSON만.
{{
    "card_name": "카드명",
    "card_company": "카드사명",
    "annual_fee": 연회비(숫자),
    "calculation_method": "이 카드에 적용한 계산 전략 요약 (1~2문장)",
    "details": [
        {{
            "category": "Coffee",
            "spending": 50000,
            "benefit_type": "할인/적립/캐시백",
            "rate_or_amount": "5% 또는 건당 300원 등 원본 표현",
            "calculation": "50000 × 0.05 = 2500",
            "monthly_limit": 5000,
            "discount": 2500,
            "reasoning": "카페 카테고리 5% 할인, 월 한도 5000원 이내"
        }}
    ],
    "unclear_benefits": ["계산 불가능한 혜택 설명"],
    "total_monthly_benefit": 합계(숫자),
    "total_yearly_benefit": 합계×12(숫자)
}}
"""

LLM_FILTER_PROMPT_V1 = """
너는 신용카드 추천 시스템의 '필터링 & 스코어링' 전문가다.

[유저 소비 패턴]
월 총 소비: {total_budget:,}원
카테고리별 소비:
{spending_lines}

[전체 카드 목록 (요약)]
{cards_summary}

[작업]
위 유저의 소비 패턴을 기반으로, 가장 적합한 카드 7개를 선정해줘.

[선정 기준]
1. 전월실적 충족 여부: 유저의 월 총 소비({total_budget:,}원)가 카드의 minimum_performance 이상이어야 함
2. 카테고리 매칭: 유저의 소비 카테고리와 카드의 혜택 카테고리가 겹칠수록 좋음
3. 혜택 실질성: 단순 카테고리 겹침뿐만 아니라, 유저의 실제 소비 금액 대비 혜택이 의미 있는지 판단
4. 연회비 대비 가성비: 연회비가 높더라도 혜택이 크면 선정 가능

[출력 형식] 반드시 아래 JSON 포맷만 출력하세요. 마크다운이나 설명 없이 JSON만.
{{
    "selected_cards": [
        {{
            "card_name": "카드명",
            "reason": "선정 이유 (1문장)",
            "relevance_score": 0.0~1.0
        }}
    ]
}}

- selected_cards는 정확히 7개 (적합한 카드가 7개 미만이면 있는 만큼만)
- relevance_score 기준으로 내림차순 정렬
- card_name은 입력 데이터의 card_name과 정확히 일치해야 함
"""


# ===========================< State >============================

class AgentState(TypedDict):
    messages: Annotated[List[AnyMessage], add_messages]
    total_budget: NotRequired[Optional[int]]
    category_spending: NotRequired[Optional[Dict[str, int]]]
    # 중간 결과
    all_cards: NotRequired[Optional[list]]
    shortlist_cards: NotRequired[Optional[list]]
    calc_results: NotRequired[Optional[list]]
    # LLM 필터 결과 (실험 추적용)
    llm_filter_raw: NotRequired[Optional[str]]
    # 최종 결과
    recommended_cards: NotRequired[Optional[list]]
    last_raw_data: NotRequired[Optional[str]]


# ===========================< Nodes >============================

@observe(name="exp_llm_filter")
@traceable(run_type="chain", name="exp_llm_filter")
def llm_filter_node(state: AgentState):
    """LLM이 직접 카드를 필터링하고 Top 7을 선정합니다."""
    _node_start = time.time()
    print("[EXP] llm_filter_node")
    total_budget = state.get("total_budget", 0)
    category_spending = state.get("category_spending", {})

    all_cards = load_all_cards()

    # 카드 요약 정보 생성 (LLM에 전달할 최소한의 정보)
    cards_summary_lines = []
    for i, card in enumerate(all_cards):
        categories = card.get("card_categories", [])
        benefits_preview = []
        for b in card.get("benefits", [])[:3]:  # 상위 3개 혜택만 요약
            cat = b.get("category", "")
            rate = b.get("rate") or 0
            benefit_type = b.get("benefit_type", "")
            if rate > 0:
                benefits_preview.append(f"{cat}:{benefit_type} {rate*100:.0f}%")

        cards_summary_lines.append(
            f"{i+1}. {card['card_name']} | "
            f"전월실적: {card.get('minimum_performance', 0):,}원 | "
            f"연회비: {card.get('annual_fee', 0):,}원 | "
            f"카테고리: {', '.join(categories)} | "
            f"주요혜택: {', '.join(benefits_preview) if benefits_preview else '상세 확인 필요'}"
        )

    spending_lines = "\n".join(
        f"- {cat}: 월 {amt:,}원" for cat, amt in category_spending.items()
    )

    prompt = LLM_FILTER_PROMPT_V1.format(
        total_budget=total_budget,
        spending_lines=spending_lines,
        cards_summary="\n".join(cards_summary_lines),
    )

    response = llm.invoke([SystemMessage(content=prompt)])
    raw_response = response.content if isinstance(response.content, str) else str(response.content)

    print(f"  전체 {len(all_cards)}개 카드 중 LLM 선별 중...")

    # JSON 파싱
    try:
        cleaned = raw_response.replace("```json", "").replace("```", "").strip()
        result = json.loads(cleaned)
        selected = result.get("selected_cards", [])
    except json.JSONDecodeError:
        print(f"  [WARN] LLM JSON 파싱 실패, 코드 기반 폴백 적용")
        selected = []

    # 선정된 카드 매칭
    card_map = {card["card_name"]: card for card in all_cards}
    shortlist = []
    for item in selected:
        card_name = item.get("card_name", "")
        if card_name in card_map:
            card = card_map[card_name]
            card["_llm_reason"] = item.get("reason", "")
            card["_llm_relevance"] = item.get("relevance_score", 0)
            shortlist.append(card)

    print(f"  LLM 선정 결과: {len(shortlist)}개 카드")
    for i, card in enumerate(shortlist):
        print(f"    {i+1}. {card['card_name']} (relevance={card.get('_llm_relevance', 'N/A')}) - {card.get('_llm_reason', '')}")

    # 테스트 로그
    _test_log["llm_filter_result"] = {
        "total_cards": len(all_cards),
        "selected_count": len(shortlist),
        "selected": [
            {
                "card_name": c["card_name"],
                "reason": c.get("_llm_reason", ""),
                "relevance_score": c.get("_llm_relevance", 0),
            }
            for c in shortlist
        ],
        "llm_raw": raw_response,
        "elapsed_seconds": round(time.time() - _node_start, 2),
    }
    print(f"  [TIME] llm_filter: {_test_log['llm_filter_result']['elapsed_seconds']}초")

    if not shortlist:
        return {
            "messages": [AIMessage(
                content=f"월 소비 {total_budget:,}원 기준으로 적합한 카드를 찾지 못했습니다."
            )],
            "shortlist_cards": [],
            "all_cards": all_cards,
            "llm_filter_raw": raw_response,
        }

    return {
        "shortlist_cards": shortlist,
        "all_cards": all_cards,
        "llm_filter_raw": raw_response,
    }


@observe(name="exp_llm_calculate")
@traceable(run_type="chain", name="exp_llm_calculate")
def calculate_benefits_node(state: AgentState):
    """LLM이 카드 원본 데이터를 분석하고 계산 방법을 스스로 결정합니다."""
    _node_start = time.time()
    print("[EXP] llm_calculate_benefits_node")
    shortlist = state.get("shortlist_cards", [])
    category_spending = state.get("category_spending", {})
    total_budget = state.get("total_budget", 0)

    spending_lines = "\n".join(
        f"- {cat}: 월 {amt:,}원" for cat, amt in category_spending.items()
    )

    calc_results = []
    for card in shortlist:
        card_digest = load_digest(card)

        # 구조화 데이터에서 내부 필드 제거 후 전달
        card_json_data = {k: v for k, v in card.items() if not k.startswith("_")}

        prompt = LLM_CALC_PROMPT_V1.format(
            total_budget=total_budget,
            spending_lines=spending_lines,
            card_digest=card_digest,
            card_json=json.dumps(card_json_data, ensure_ascii=False, indent=2),
        )

        response = llm.invoke([SystemMessage(content=prompt)])
        raw = response.content if isinstance(response.content, str) else str(response.content)

        # JSON 파싱
        try:
            cleaned = raw.replace("```json", "").replace("```", "").strip()
            result = json.loads(cleaned)
        except json.JSONDecodeError:
            print(f"  [WARN] {card['card_name']} 계산 JSON 파싱 실패")
            result = {}

        monthly = result.get("total_monthly_benefit", 0)
        yearly = result.get("total_yearly_benefit", monthly * 12)

        calc_results.append({
            "card_name": result.get("card_name", card.get("card_name")),
            "card_company": result.get("card_company", card.get("card_company")),
            "annual_fee": result.get("annual_fee", card.get("annual_fee", 0)),
            "minimum_performance": card.get("minimum_performance", 0),
            "expected_monthly_benefit": monthly,
            "expected_yearly_benefit": yearly,
            "benefits_breakdown": result.get("details", []),
            "calculation_method": result.get("calculation_method", ""),
            "unclear_benefits": result.get("unclear_benefits", []),
            "_llm_reason": card.get("_llm_reason", ""),
            "_llm_relevance": card.get("_llm_relevance", 0),
            "_digest_path": card.get("_digest_path", ""),
            "_card_data": card,
            "_calc_raw": raw,
        })

        print(f"  {card['card_name']}: 월 {monthly:,}원 | 방법: {result.get('calculation_method', 'N/A')}")

    _calc_elapsed = round(time.time() - _node_start, 2)
    _test_log["calc_results"] = [
        {
            "card_name": r["card_name"],
            "expected_monthly_benefit": r["expected_monthly_benefit"],
            "calculation_method": r["calculation_method"],
            "benefits_breakdown": r["benefits_breakdown"],
            "unclear_benefits": r["unclear_benefits"],
            "llm_reason": r["_llm_reason"],
            "llm_relevance": r["_llm_relevance"],
        }
        for r in calc_results
    ]
    _test_log["calc_elapsed_seconds"] = _calc_elapsed
    print(f"  [TIME] llm_calculate: {_calc_elapsed}초")

    return {"calc_results": calc_results}


@observe(name="exp_rank_and_explain")
def rank_and_explain_node(state: AgentState):
    """최종 랭킹 후 LLM 추천 설명을 생성합니다."""
    _node_start = time.time()
    print("[EXP] rank_and_explain_node")
    calc_results = state.get("calc_results", [])
    category_spending = state.get("category_spending", {})
    total_budget = state.get("total_budget", 0)

    if not calc_results:
        return {"messages": [AIMessage(content="혜택 계산 결과가 없습니다.")]}

    # 최종 랭킹: 혜택 금액 기준 Top 3
    ranked = sorted(calc_results, key=lambda x: x["expected_monthly_benefit"], reverse=True)[:3]

    # 유저 소비 패턴 텍스트
    spending_lines = [f"월 총 소비: {total_budget:,}원"]
    for cat, amount in category_spending.items():
        spending_lines.append(f"- {cat}: 월 {amount:,}원")
    user_spending = "\n".join(spending_lines)

    # 1순위 카드 digest
    top1 = ranked[0]
    card_digest = load_digest(top1.get("_card_data", {}))

    # calc_summary
    breakdown_lines = []
    for b in top1["benefits_breakdown"]:
        breakdown_lines.append(f"  - {b['category']}: {b.get('amount', b.get('discount', 0)):,}원")
    calc_summary = (
        f"카드: {top1['card_name']} ({top1['card_company']})\n"
        f"연회비: {top1['annual_fee']:,}원\n"
        f"월 예상 할인: {top1['expected_monthly_benefit']:,}원 | "
        f"연간 예상: {top1['expected_yearly_benefit']:,}원\n"
        + "\n".join(breakdown_lines)
    )

    explain_prompt = EXPLAIN_PROMPT.format(
        user_spending=user_spending,
        card_digest=card_digest,
        calc_summary=calc_summary,
    )
    explanation = llm.invoke([SystemMessage(content=explain_prompt)]).content

    # 테스트 로그
    _test_log["top3"] = [
        {
            "card_name": r["card_name"],
            "expected_monthly_benefit": r["expected_monthly_benefit"],
            "benefits_breakdown": r["benefits_breakdown"],
            "llm_reason": r.get("_llm_reason", ""),
            "llm_relevance": r.get("_llm_relevance", 0),
        }
        for r in ranked
    ]
    _test_log["explain_raw"] = explanation if isinstance(explanation, str) else str(explanation)

    # 응답 구성
    response_parts = []
    for i, card in enumerate(ranked):
        rank_label = ["1순위", "2순위", "3순위"][i]
        monthly = card["expected_monthly_benefit"]
        yearly = card["expected_yearly_benefit"]
        annual_fee = card["annual_fee"]
        net_benefit = yearly - annual_fee

        details = []
        for b in card["benefits_breakdown"]:
            details.append(f"  - {b['category']}: {b.get('amount', b.get('discount', 0)):,}원")

        section = f"[{rank_label}] {card['card_name']} ({card['card_company']})\n"
        section += f"연회비: {annual_fee:,}원 | 월 예상 할인: {monthly:,}원 | 연 순이익 추정: {net_benefit:,}원\n"
        if card.get("_llm_reason"):
            section += f"  [LLM 선정 이유] {card['_llm_reason']}\n"
        if details:
            section += "\n".join(details) + "\n"

        unclear = card.get("unclear_benefits", [])
        if unclear:
            section += f"  [���고] 추가 혜택 {len(unclear)}건 (계산 미포함)\n"

        response_parts.append(section)

    final_response = "\n".join(response_parts)
    final_response += f"\n{'=' * 40}\n{explanation}"

    recommended_cards = [
        {
            "card_name": r["card_name"],
            "card_company": r["card_company"],
            "annual_fee": r["annual_fee"],
            "minimum_performance": r["minimum_performance"],
            "expected_monthly_benefit": r["expected_monthly_benefit"],
            "benefits_breakdown": r["benefits_breakdown"],
            "llm_reason": r.get("_llm_reason", ""),
            "explanation": explanation if i == 0 else "",
        }
        for i, r in enumerate(ranked)
    ]

    _explain_elapsed = round(time.time() - _node_start, 2)
    _test_log["explain_elapsed_seconds"] = _explain_elapsed
    print(f"  [TIME] rank_and_explain: {_explain_elapsed}초")

    return {
        "messages": [AIMessage(content=final_response)],
        "recommended_cards": recommended_cards,
        "last_raw_data": json.dumps(recommended_cards, ensure_ascii=False),
    }


@observe(name="exp_answer_qa")
def answer_qa_node(state: AgentState):
    """후속 질문 답변."""
    print("[EXP] answer_qa_node")
    raw_data = state.get("last_raw_data", "이전 검색 결과 원본이 존재하지 않습니다.")
    qa_prompt = QA_PROMPT.format(raw_data=raw_data)
    response = llm.invoke([SystemMessage(content=qa_prompt)] + state["messages"])
    return {"messages": [AIMessage(content=response.content)]}


# ===========================< Edge Logic >============================

def check_filter_result(state: AgentState) -> Literal["calculate", "no_results"]:
    filtered = state.get("shortlist_cards", [])
    return "calculate" if filtered else "no_results"


# ===========================< Graph Construction >============================

workflow = StateGraph(AgentState)

workflow.add_node("llm_filter", llm_filter_node)
workflow.add_node("calculate_benefits", calculate_benefits_node)
workflow.add_node("rank_and_explain", rank_and_explain_node)
workflow.add_node("answer_qa", answer_qa_node)

# 메인 흐름: LLM 필터 → 코드 계산 → 설명 → END
workflow.add_edge(START, "llm_filter")
workflow.add_conditional_edges(
    "llm_filter",
    check_filter_result,
    {
        "calculate": "calculate_benefits",
        "no_results": END,
    },
)
workflow.add_edge("calculate_benefits", "rank_and_explain")
workflow.add_edge("rank_and_explain", END)
workflow.add_edge("answer_qa", END)

memory = InMemorySaver()
app = workflow.compile(checkpointer=memory)


# ===========================< Test Execution >============================

if __name__ == "__main__":
    TEST_CASES = {
        "1": {
            "name": "카페 + 교통 위주 소비자",
            "total_budget": 500000,
            "category_spending": {"Coffee": 50000, "Traffic": 100000, "Shopping": 150000},
        },
        "2": {
            "name": "여행 + 쇼핑 고소비자",
            "total_budget": 1000000,
            "category_spending": {"Travel": 300000, "Shopping": 200000, "Food": 200000},
        },
        "3": {
            "name": "생활비 중심 알뜰 소비자",
            "total_budget": 300000,
            "category_spending": {"Traffic": 50000, "Shopping": 30000, "Food": 100000},
        },
        "4": {
            "name": "주유 + 차량 관리 위주",
            "total_budget": 700000,
            "category_spending": {"Traffic": 150000, "Shopping": 200000, "Life": 100000},
        },
    }

    def run_test(case_id: str):
        case = TEST_CASES[case_id]
        print(f"\n{'=' * 20} [실험 테스트: {case['name']}] {'=' * 20}")
        print(f"  총 월소비: {case['total_budget']:,}원")
        for cat, amt in case["category_spending"].items():
            print(f"  - {cat}: {amt:,}원")
        print()

        _init_test_log(case["total_budget"], case["category_spending"])
        start_time = time.time()

        session_id = f"exp_{uuid.uuid4().hex[:6]}"
        config: RunnableConfig = {"configurable": {"thread_id": session_id}}

        inputs: AgentState = {
            "messages": [],
            "total_budget": case["total_budget"],
            "category_spending": case["category_spending"],
        }

        for event in app.stream(inputs, config=config):
            for key, value in event.items():
                if "messages" in value and value["messages"]:
                    print(f"[{key}] {value['messages'][-1].content}")
                if "shortlist_cards" in value:
                    print(f"  [LLM 필터] {len(value['shortlist_cards'])}개 카드 선정")

        elapsed = time.time() - start_time
        _test_log["elapsed_seconds"] = round(elapsed, 2)
        print(f"\n[TIME] 소요 시간: {elapsed:.1f}초")

        _save_test_log(case["name"])
        print(f"{'=' * 60}\n")

    # 인터랙티브 메뉴
    while True:
        print("\n[실험] 테스트 케이스를 선택하세요:")
        for k, v in TEST_CASES.items():
            print(f"  [{k}] {v['name']} (월 {v['total_budget']:,}원)")
        print("  [q] 종료")

        cmd = input("번호 입력: ").strip().lower()
        if cmd == "q":
            print("테스트를 종료합니다.")
            break
        elif cmd in TEST_CASES:
            run_test(cmd)
        else:
            print("[WARN] 잘못된 입력입니다.")
