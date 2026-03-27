"""
실험 E: 스코어링 필터 없이 전체 카드 계산 비교

흐름: 유저 입력 → 필터링(전월실적+카테고리) → 전체 카드 계산 → 랭킹 → LLM 설명
llmrun.py와 동일하되 Top7 스코어링 단계를 제거하고,
필터 통과한 모든 카드에 대해 계산을 수행합니다.
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

REQUIRED_KEYS = ["LANGSMITH_API_KEY", "UPSTAGE_API_KEY", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"]
for key in REQUIRED_KEYS:
    if not os.getenv(key):
        print(f"[WARN] {key}가 환경 변수에 설정되지 않았습니다.")

os.environ["LANGSMITH_TRACING_V2"] = "true"
os.environ["LANGSMITH_PROJECT"] = "Smart_Pick_Exp_E"
os.environ["LANGSMITH_ENDPOINT"] = "https://api.smith.langchain.com"

langfuse = Langfuse()

MODEL = "solar-pro2"
llm = init_chat_model(model=MODEL, temperature=0.0)

# ===========================< Test Log >============================
TEST_LOG_DIR = Path(__file__).resolve().parents[3] / "test_logs" / "exp_e"
PROMPT_VERSIONS = {"EXPLAIN_PROMPT": "V3", "QA_PROMPT": "V1"}

_test_log: dict = {}


def _init_test_log(total_budget: int, category_spending: dict):
    global _test_log
    _test_log = {
        "timestamp": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "model": MODEL,
        "experiment": "E (no scoring filter)",
        "prompt_versions": PROMPT_VERSIONS,
        "input": {
            "total_budget": total_budget,
            "category_spending": category_spending,
        },
        "filter": {},
        "all_calc_results": [],
        "top3": [],
        "explain_raw": "",
    }


def _save_test_log(case_name: str):
    TEST_LOG_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = case_name.replace(" ", "_").replace("+", "")
    filepath = TEST_LOG_DIR / f"{ts}_{safe_name}.json"
    filepath.write_text(json.dumps(_test_log, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[LOG] 테스트 로그 저장: {filepath}")

# ===========================< Data Loading >============================

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


# ===========================< State >============================

class AgentState(TypedDict):
    messages: Annotated[List[AnyMessage], add_messages]
    total_budget: NotRequired[Optional[int]]
    category_spending: NotRequired[Optional[Dict[str, int]]]
    filtered_cards: NotRequired[Optional[list]]
    calc_results: NotRequired[Optional[list]]
    recommended_cards: NotRequired[Optional[list]]
    last_raw_data: NotRequired[Optional[str]]


# ===========================< Nodes >============================

@observe(name="exp_e_filter_cards")
@traceable(run_type="chain", name="exp_e_filter_cards")
def filter_cards_node(state: AgentState):
    """전월실적 + 카테고리 겹침 기준으로 카드를 필터링합니다. (스코어링 없음)"""
    start = time.time()
    print("[DEBUG] filter_cards_node (exp_e: no scoring)")
    total_budget = state.get("total_budget", 0)
    category_spending = state.get("category_spending", {})
    user_categories = set(category_spending.keys())

    all_cards = load_all_cards()

    # 필터 A: 전월실적 충족
    after_performance = [
        card for card in all_cards
        if card.get("minimum_performance", 0) <= total_budget
    ]

    # 필터 B: 카테고리 겹침
    filtered = [
        card for card in after_performance
        if user_categories & set(card.get("card_categories", []))
    ]

    elapsed = time.time() - start
    print(f"  전체 {len(all_cards)}개 → 실적 충족 {len(after_performance)}개 → 카테고리 매칭 {len(filtered)}개")
    print(f"  [TIME] filter: {elapsed:.2f}초")

    _test_log["filter"] = {
        "total_cards": len(all_cards),
        "after_performance": len(after_performance),
        "after_category": len(filtered),
        "elapsed_seconds": round(elapsed, 3),
    }

    if not filtered:
        return {
            "messages": [AIMessage(
                content=f"월 소비 {total_budget:,}원 기준으로 조건을 충족하는 카드가 없습니다."
            )],
            "filtered_cards": [],
        }

    # 스코어링 없이 전체 통과 카드 출력
    print(f"\n  === 필터 통과 카드 ({len(filtered)}장, 스코어링 없이 전체 계산 진행) ===")
    for i, card in enumerate(filtered):
        print(f"    {i+1:2d}. {card['card_name']}")

    return {"filtered_cards": filtered}


@observe(name="exp_e_calculate_benefits")
@traceable(run_type="chain", name="exp_e_calculate_benefits")
def calculate_benefits_node(state: AgentState):
    """필터 통과한 전체 카드에 대해 혜택 금액을 계산합니다."""
    start = time.time()
    print("[DEBUG] calculate_benefits_node (exp_e: all filtered cards)")
    filtered_cards = state.get("filtered_cards", [])
    category_spending = state.get("category_spending", {})

    calc_results = []
    for card in filtered_cards:
        benefits_breakdown = []
        total_monthly = 0

        for benefit in card.get("benefits", []):
            cat = benefit.get("category", "")
            spend = category_spending.get(cat, 0)
            rate = benefit.get("rate", 0)
            monthly_limit = benefit.get("monthly_limit")

            if not spend or not rate or spend <= 0 or rate <= 0:
                continue

            raw_amount = spend * rate
            if monthly_limit and monthly_limit > 0:
                amount = min(raw_amount, monthly_limit)
            else:
                amount = raw_amount

            amount = int(amount)
            benefits_breakdown.append({
                "category": cat,
                "benefit_type": benefit.get("benefit_type", ""),
                "amount": amount,
            })
            total_monthly += amount

        calc_results.append({
            "card_name": card.get("card_name"),
            "card_company": card.get("card_company"),
            "annual_fee": card.get("annual_fee", 0),
            "minimum_performance": card.get("minimum_performance", 0),
            "expected_monthly_benefit": total_monthly,
            "expected_yearly_benefit": total_monthly * 12,
            "benefits_breakdown": benefits_breakdown,
            "unclear_benefits": card.get("unclear_benefits", []),
            "_digest_path": card.get("_digest_path", ""),
            "_card_data": card,
        })

    # 혜택 금액 기준 정렬
    calc_results.sort(key=lambda x: x["expected_monthly_benefit"], reverse=True)

    elapsed = time.time() - start
    print(f"\n  === 전체 계산 결과 ({len(calc_results)}장) ===")
    for i, r in enumerate(calc_results):
        marker = "★" if i < 3 else " "
        print(f"    {marker} {i+1:2d}. {r['card_name']}: 월 {r['expected_monthly_benefit']:,}원 (혜택 {len(r['benefits_breakdown'])}개)")
    print(f"  [TIME] calculate: {elapsed:.2f}초")

    _test_log["all_calc_results"] = [
        {
            "rank": i + 1,
            "card_name": r["card_name"],
            "card_company": r["card_company"],
            "expected_monthly_benefit": r["expected_monthly_benefit"],
            "benefits_breakdown": r["benefits_breakdown"],
        }
        for i, r in enumerate(calc_results)
    ]

    return {"calc_results": calc_results}


@observe(name="exp_e_rank_and_explain")
def rank_and_explain_node(state: AgentState):
    """최종 랭킹 후 digest 기반으로 LLM 추천 설명을 생성합니다."""
    start = time.time()
    print("[DEBUG] rank_and_explain_node (exp_e)")
    calc_results = state.get("calc_results", [])
    category_spending = state.get("category_spending", {})
    total_budget = state.get("total_budget", 0)

    if not calc_results:
        return {
            "messages": [AIMessage(content="혜택 계산 결과가 없습니다.")]
        }

    # 이미 정렬됨 → Top 3
    ranked = calc_results[:3]

    # 유저 소비 패턴 텍스트
    spending_lines = [f"월 총 소비: {total_budget:,}원"]
    for cat, amount in category_spending.items():
        spending_lines.append(f"- {cat}: 월 {amount:,}원")
    user_spending = "\n".join(spending_lines)

    # 1순위 카드의 digest 로드
    top1 = ranked[0]
    card_digest = load_digest(top1.get("_card_data", {}))

    # calc_summary 텍스트 생성
    breakdown_lines = []
    for b in top1["benefits_breakdown"]:
        breakdown_lines.append(f"  - {b['category']}: {b['amount']:,}원")
    calc_summary = (
        f"카드: {top1['card_name']} ({top1['card_company']})\n"
        f"연회비: {top1['annual_fee']:,}원\n"
        f"월 예상 할인: {top1['expected_monthly_benefit']:,}원 | "
        f"연간 예상: {top1['expected_yearly_benefit']:,}원\n"
        + "\n".join(breakdown_lines)
    )

    # LLM 추천 설명 생성
    explain_prompt = EXPLAIN_PROMPT.format(
        user_spending=user_spending,
        card_digest=card_digest,
        calc_summary=calc_summary,
    )
    explanation = llm.invoke([SystemMessage(content=explain_prompt)]).content

    elapsed = time.time() - start
    print(f"  [TIME] rank_and_explain: {elapsed:.2f}초")

    # 테스트 로그
    _test_log["top3"] = [
        {
            "card_name": r["card_name"],
            "expected_monthly_benefit": r["expected_monthly_benefit"],
            "benefits_breakdown": r["benefits_breakdown"],
        }
        for r in ranked
    ]
    _test_log["explain_raw"] = explanation if isinstance(explanation, str) else str(explanation)

    # 최종 응답 구성
    response_parts = []
    for i, card in enumerate(ranked):
        rank_label = ["1순위", "2순위", "3순위"][i]
        monthly = card["expected_monthly_benefit"]
        yearly = card["expected_yearly_benefit"]
        annual_fee = card["annual_fee"]
        net_benefit = yearly - annual_fee

        details = []
        for b in card["benefits_breakdown"]:
            details.append(f"  - {b['category']}: {b['amount']:,}원")

        section = f"[{rank_label}] {card['card_name']} ({card['card_company']})\n"
        section += f"연회비: {annual_fee:,}원 | 월 예상 할인: {monthly:,}원 | 연 순이익 추정: {net_benefit:,}원\n"
        if details:
            section += "\n".join(details) + "\n"

        unclear = card.get("unclear_benefits", [])
        if unclear:
            section += f"  [참고] 추가 혜택 {len(unclear)}건 (계산 미포함)\n"

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
            "explanation": explanation if i == 0 else "",
        }
        for i, r in enumerate(ranked)
    ]

    return {
        "messages": [AIMessage(content=final_response)],
        "recommended_cards": recommended_cards,
        "last_raw_data": json.dumps(recommended_cards, ensure_ascii=False),
    }


# ===========================< Edge Logic >============================

def check_filter_result(state: AgentState) -> Literal["calc", "no_results"]:
    filtered = state.get("filtered_cards", [])
    return "calc" if filtered else "no_results"


# ===========================< Graph Construction >============================

workflow = StateGraph(AgentState)

workflow.add_node("filter_cards", filter_cards_node)
workflow.add_node("calculate_benefits", calculate_benefits_node)
workflow.add_node("rank_and_explain", rank_and_explain_node)

# 메인 흐름: filter → calculate → explain → END (스코어링 단계 없음)
workflow.add_edge(START, "filter_cards")
workflow.add_conditional_edges(
    "filter_cards",
    check_filter_result,
    {
        "calc": "calculate_benefits",
        "no_results": END,
    },
)
workflow.add_edge("calculate_benefits", "rank_and_explain")
workflow.add_edge("rank_and_explain", END)

memory = InMemorySaver()
app = workflow.compile(checkpointer=memory)

# ===========================< Test Execution >============================

if __name__ == "__main__":
    TEST_CASES = {
        "1": {
            "name": "카페__교통_위주_소비자",
            "total_budget": 500000,
            "category_spending": {"Coffee": 50000, "Traffic": 100000, "Shopping": 150000},
        },
        "2": {
            "name": "여행__쇼핑_고소비자",
            "total_budget": 1000000,
            "category_spending": {"Travel": 300000, "Shopping": 200000, "Food": 200000},
        },
        "3": {
            "name": "생활비_중심_알뜰_소비자",
            "total_budget": 300000,
            "category_spending": {"Traffic": 50000, "Shopping": 30000, "Food": 100000},
        },
        "4": {
            "name": "주유__차량_관리_위주",
            "total_budget": 700000,
            "category_spending": {"Traffic": 150000, "Shopping": 200000, "Life": 100000},
        },
    }

    def run_test(case_id: str):
        case = TEST_CASES[case_id]
        print(f"\n{'=' * 20} [Exp E 테스트: {case['name']}] {'=' * 20}")
        print(f"  총 월소비: {case['total_budget']:,}원")
        for cat, amt in case["category_spending"].items():
            print(f"  - {cat}: {amt:,}원")
        print()

        _init_test_log(case["total_budget"], case["category_spending"])

        start_time = time.time()

        session_id = f"exp_e_{uuid.uuid4().hex[:6]}"
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
                if "filtered_cards" in value:
                    print(f"  [필터 결과] {len(value['filtered_cards'])}개 카드 통과 (전체 계산 진행)")

        elapsed = time.time() - start_time
        _test_log["elapsed_seconds"] = round(elapsed, 2)
        print(f"\n[TIME] 총 소요 시간: {elapsed:.1f}초")

        _save_test_log(case["name"])
        print(f"{'=' * 60}\n")

    # 인터랙티브 메뉴
    while True:
        print("\n[Exp E] 테스트 케이스를 선택하세요 (스코어링 필터 없음):")
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
