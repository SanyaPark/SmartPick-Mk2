"""
계산 기반 카드 추천 로직 (v2)

흐름: 유저 입력 → 필터링 → 스코어링(Top7) → 코드 계산 → 랭킹 → LLM 설명
기존 agent.py(대화형)와 독립적으로 동작합니다.
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
os.environ["LANGSMITH_PROJECT"] = "Smart_Pick"
os.environ["LANGSMITH_ENDPOINT"] = "https://api.smith.langchain.com"

# LangFuse 초기화 (OTEL 기반 자동 계측)
langfuse = Langfuse()

MODEL = "solar-pro2"
llm = init_chat_model(model=MODEL, temperature=0.0)

# ===========================< Test Log >============================
TEST_LOG_DIR = Path(__file__).resolve().parents[3] / "test_logs" / "llmrun_test"
PROMPT_VERSIONS = {"EXPLAIN_PROMPT": "V3", "QA_PROMPT": "V1"}

_test_log: dict = {}


def _init_test_log(total_budget: int, category_spending: dict):
    """테스트 로그 초기화."""
    global _test_log
    _test_log = {
        "timestamp": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "model": MODEL,
        "prompt_versions": PROMPT_VERSIONS,
        "input": {
            "total_budget": total_budget,
            "category_spending": category_spending,
        },
        "filter": {},
        "scores": [],
        "calc_results": [],
        "top3": [],
        "explain_raw": "",
    }


def _save_test_log(case_name: str):
    """테스트 로그를 JSON 파일로 저장."""
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
    """datasets/json_v2/ 하위의 모든 카드 JSON을 로드합니다."""
    all_cards = []
    for company_dir in DATASETS_DIR.iterdir():
        if not company_dir.is_dir():
            continue
        for json_file in company_dir.glob("*.json"):
            data = json.loads(json_file.read_text(encoding="utf-8"))
            if not data.get("card_name"):
                continue
            # digest 파일 경로 저장
            digest_path = DIGEST_DIR / company_dir.name / f"{json_file.stem}.md"
            data["_digest_path"] = str(digest_path)
            data["_file_stem"] = json_file.stem
            all_cards.append(data)
    return all_cards


def load_digest(card: dict) -> str:
    """카드의 compact digest 마크다운을 로드합니다."""
    digest_path = Path(card.get("_digest_path", ""))
    if digest_path.exists():
        return digest_path.read_text(encoding="utf-8")
    return f"# {card.get('card_name', '알 수 없음')}\n(digest 파일 없음)"


# ===========================< State >============================

class AgentState(TypedDict):
    messages: Annotated[List[AnyMessage], add_messages]
    # 유저 입력
    total_budget: NotRequired[Optional[int]]
    category_spending: NotRequired[Optional[Dict[str, int]]]
    # 중간 결과
    filtered_cards: NotRequired[Optional[list]]
    shortlist_cards: NotRequired[Optional[list]]
    calc_results: NotRequired[Optional[list]]
    # 최종 결과
    recommended_cards: NotRequired[Optional[list]]
    last_raw_data: NotRequired[Optional[str]]


# ===========================< Nodes >============================

@observe(name="filter_cards")
@traceable(run_type="chain", name="filter_cards")
def filter_cards_node(state: AgentState):
    """전월실적 + 카테고리 겹침 기준으로 카드를 필터링합니다."""
    print("[DEBUG] filter_cards_node")
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

    print(f"  전체 {len(all_cards)}개 → 실적 충족 {len(after_performance)}개 → 카테고리 매칭 {len(filtered)}개")

    _test_log["filter"]["total_cards"] = len(all_cards)
    _test_log["filter"]["after_performance"] = len(after_performance)
    _test_log["filter"]["after_category"] = len(filtered)

    if not filtered:
        return {
            "messages": [AIMessage(
                content=f"월 소비 {total_budget:,}원 기준으로 조건을 충족하는 카드가 없습니다."
            )],
            "filtered_cards": [],
        }

    return {"filtered_cards": filtered}


@observe(name="score_and_shortlist")
@traceable(run_type="chain", name="score_and_shortlist")
def score_and_shortlist_node(state: AgentState):
    """카드 점수 계산 후 Top 7을 선정합니다."""
    print("[DEBUG] score_and_shortlist_node")
    filtered_cards = state.get("filtered_cards", [])
    category_spending = state.get("category_spending", {})
    total_budget = state.get("total_budget", 0)
    user_categories = set(category_spending.keys())

    scored_cards = []
    for card in filtered_cards:
        card_categories = set(card.get("card_categories", []))
        overlapping = user_categories & card_categories

        # min_spend_score: 낮을수록 좋음 (전월실적 부담도)
        min_perf = card.get("minimum_performance", 0)
        min_spend_score = min_perf / total_budget if total_budget > 0 else 1.0

        # fit_score: 높을수록 좋음 (카테고리 매칭 비율)
        fit_score = len(overlapping) / len(user_categories) if user_categories else 0.0

        # coverage_score: 높을수록 좋음 (매칭 카테고리의 소비 비율)
        covered_spend = sum(category_spending.get(cat, 0) for cat in overlapping)
        coverage_score = covered_spend / total_budget if total_budget > 0 else 0.0

        # 종합 점수: fit과 coverage는 높을수록, min_spend는 낮을수록 좋음
        total_score = (fit_score * 0.3) + (coverage_score * 0.5) + ((1 - min_spend_score) * 0.2)

        scored_cards.append({
            **card,
            "_scores": {
                "min_spend_score": round(min_spend_score, 3),
                "fit_score": round(fit_score, 3),
                "coverage_score": round(coverage_score, 3),
                "total_score": round(total_score, 3),
            },
        })

    # 점수 기준 정렬 → Top 7 (동점 카드 포함)
    scored_cards.sort(key=lambda x: x["_scores"]["total_score"], reverse=True)
    if len(scored_cards) >= 7:
        cutoff_score = scored_cards[6]["_scores"]["total_score"]
        shortlist = [c for c in scored_cards if c["_scores"]["total_score"] >= cutoff_score]
    else:
        shortlist = scored_cards[:]
    shortlist_names = {c["card_name"] for c in shortlist}

    print(f"\n  === 전체 카드 스코어 ({len(scored_cards)}장) ===")
    for i, card in enumerate(scored_cards):
        s = card["_scores"]
        marker = "★" if card["card_name"] in shortlist_names else " "
        print(f"    {marker} {i+1:2d}. {card['card_name']}")
        print(f"         total={s['total_score']}  fit={s['fit_score']}  coverage={s['coverage_score']}  min_spend={s['min_spend_score']}")
    if len(scored_cards) > len(shortlist):
        print(f"\n  ── 컷라인: total_score >= {cutoff_score} ──")
        print(f"  ── 선정: {len(shortlist)}장 (동점 포함) | 탈락: {len(scored_cards) - len(shortlist)}장 ──")

    _test_log["scores"] = [
        {"card_name": c["card_name"], "selected": c["card_name"] in shortlist_names, **c["_scores"]}
        for c in scored_cards
    ]

    return {"shortlist_cards": shortlist}


@observe(name="calculate_benefits")
@traceable(run_type="chain", name="calculate_benefits")
def calculate_benefits_node(state: AgentState):
    """코드로 카드별 혜택 금액을 계산합니다."""
    print("[DEBUG] calculate_benefits_node")
    shortlist = state.get("shortlist_cards", [])
    category_spending = state.get("category_spending", {})

    calc_results = []
    for card in shortlist:
        benefits_breakdown = []
        total_monthly = 0

        for benefit in card.get("benefits", []):
            cat = benefit.get("category", "")
            # General/All_Domestic은 전체 소비에 적용되는 기본 혜택
            if cat in ("General", "All_Domestic"):
                spend = sum(category_spending.values())
            else:
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
            "_scores": card.get("_scores", {}),
            "_digest_path": card.get("_digest_path", ""),
            "_card_data": card,
        })

        print(f"  {card['card_name']}: 월 {total_monthly:,}원 (혜택 {len(benefits_breakdown)}개)")

    _test_log["calc_results"] = [
        {
            "card_name": r["card_name"],
            "expected_monthly_benefit": r["expected_monthly_benefit"],
            "benefits_breakdown": r["benefits_breakdown"],
        }
        for r in calc_results
    ]

    return {"calc_results": calc_results}


@observe(name="rank_and_explain")
def rank_and_explain_node(state: AgentState):
    """최종 랭킹 후 digest 기반으로 LLM 추천 설명을 생성합니다."""
    print("[DEBUG] rank_and_explain_node")
    calc_results = state.get("calc_results", [])
    category_spending = state.get("category_spending", {})
    total_budget = state.get("total_budget", 0)

    if not calc_results:
        return {
            "messages": [AIMessage(content="혜택 계산 결과가 없습니다.")]
        }

    # 1. 최종 랭킹: 총 혜택 금액 기준 정렬 → Top 3
    ranked = sorted(calc_results, key=lambda x: x["expected_monthly_benefit"], reverse=True)[:3]

    # 2. 유저 소비 패턴 텍스트
    spending_lines = [f"월 총 소비: {total_budget:,}원"]
    for cat, amount in category_spending.items():
        spending_lines.append(f"- {cat}: 월 {amount:,}원")
    user_spending = "\n".join(spending_lines)

    # 3. 1순위 카드의 digest 로드
    top1 = ranked[0]
    card_digest = load_digest(top1.get("_card_data", {}))

    # 4. calc_summary 텍스트 생성
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

    # 5. LLM 추천 설명 생성
    explain_prompt = EXPLAIN_PROMPT.format(
        user_spending=user_spending,
        card_digest=card_digest,
        calc_summary=calc_summary,
    )
    explanation = llm.invoke([SystemMessage(content=explain_prompt)]).content

    # 6. 테스트 로그
    _test_log["top3"] = [
        {
            "card_name": r["card_name"],
            "expected_monthly_benefit": r["expected_monthly_benefit"],
            "benefits_breakdown": r["benefits_breakdown"],
            "scores": r.get("_scores", {}),
        }
        for r in ranked
    ]
    _test_log["explain_raw"] = explanation if isinstance(explanation, str) else str(explanation)

    # 7. 최종 응답 구성
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

        # unclear_benefits 표시
        unclear = card.get("unclear_benefits", [])
        if unclear:
            section += f"  [참고] 추가 혜택 {len(unclear)}건 (계산 미포함)\n"

        response_parts.append(section)

    final_response = "\n".join(response_parts)
    final_response += f"\n{'=' * 40}\n{explanation}"

    # 8. UI용 최종 데이터
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


@observe(name="answer_qa")
def answer_qa_node(state: AgentState):
    """추천된 카드에 대한 후속 질문에 답변합니다."""
    print("[DEBUG] answer_qa_node")
    raw_data = state.get("last_raw_data", "이전 검색 결과 원본이 존재하지 않습니다.")
    qa_prompt = QA_PROMPT.format(raw_data=raw_data)
    response = llm.invoke([SystemMessage(content=qa_prompt)] + state["messages"])
    return {"messages": [AIMessage(content=response.content)]}


# ===========================< Edge Logic >============================

def check_filter_result(
    state: AgentState,
) -> Literal["score", "no_results"]:
    """필터링 결과가 있으면 스코어링 진행, 없으면 종료."""
    filtered = state.get("filtered_cards", [])
    return "score" if filtered else "no_results"


# ===========================< Graph Construction >============================

workflow = StateGraph(AgentState)

workflow.add_node("filter_cards", filter_cards_node)
workflow.add_node("score_shortlist", score_and_shortlist_node)
workflow.add_node("calculate_benefits", calculate_benefits_node)
workflow.add_node("rank_and_explain", rank_and_explain_node)
workflow.add_node("answer_qa", answer_qa_node)

# 메인 흐름: filter → score → calculate → explain → END
workflow.add_edge(START, "filter_cards")
workflow.add_conditional_edges(
    "filter_cards",
    check_filter_result,
    {
        "score": "score_shortlist",
        "no_results": END,
    },
)
workflow.add_edge("score_shortlist", "calculate_benefits")
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
        print(f"\n{'=' * 20} [테스트: {case['name']}] {'=' * 20}")
        print(f"  총 월소비: {case['total_budget']:,}원")
        for cat, amt in case["category_spending"].items():
            print(f"  - {cat}: {amt:,}원")
        print()

        _init_test_log(case["total_budget"], case["category_spending"])

        # 테스트 시작 시간 측정
        start_time = time.time()

        session_id = f"test_{uuid.uuid4().hex[:6]}"
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
                    print(f"  [필터 결과] {len(value['filtered_cards'])}개 카드 통과")
                if "shortlist_cards" in value:
                    print(f"  [Top 7] {len(value['shortlist_cards'])}개 카드 선정")

        # 테스트 종료 시간 측정
        elapsed = time.time() - start_time
        _test_log["elapsed_seconds"] = round(elapsed, 2)
        print(f"\n[TIME] 소요 시간: {elapsed:.1f}초")

        _save_test_log(case["name"])
        print(f"{'=' * 60}\n")

    # 인터랙티브 메뉴
    while True:
        print("\n테스트 케이스를 선택하세요:")
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
