"""
계산 기반 카드 추천 로직 (신규 기획)

흐름: 구조화된 입력 → 전월실적 필터 → LLM 할인금액 계산 → 정렬 → LLM 추천 설명
기존 agent.py(대화형)와 독립적으로 동작합니다.
"""

import os
import json
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

from apps.backend.agent.prompts import CALC_PROMPT, EXPLAIN_PROMPT, QA_PROMPT

# ===========================< Setting >============================
load_dotenv(Path(__file__).resolve().parents[3] / ".env")

REQUIRED_KEYS = ["LANGSMITH_API_KEY", "UPSTAGE_API_KEY"]
for key in REQUIRED_KEYS:
    if not os.getenv(key):
        print(f"[WARN] {key}가 환경 변수에 설정되지 않았습니다.")

os.environ["LANGSMITH_TRACING_V2"] = "true"
os.environ["LANGSMITH_PROJECT"] = "Smart_Pick"
os.environ["LANGSMITH_ENDPOINT"] = "https://api.smith.langchain.com"

MODEL = "solar-pro2"
llm = init_chat_model(model=MODEL, temperature=0.0)

# ===========================< Test Log >============================
TEST_LOG_DIR = Path(__file__).resolve().parents[3] / "test_logs"
PROMPT_VERSIONS = {"CALC_PROMPT": "V1", "EXPLAIN_PROMPT": "V2", "QA_PROMPT": "V1"}

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
        "calc_raw": {},
        "top3": [],
        "explain_raw": "",
    }


def _save_test_log(case_name: str):
    """테스트 로그를 JSON 파일로 저장."""
    TEST_LOG_DIR.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = case_name.replace(" ", "_").replace("+", "")
    filepath = TEST_LOG_DIR / f"{ts}_{safe_name}.json"
    filepath.write_text(json.dumps(_test_log, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[LOG] 테스트 로그 저장: {filepath}")

# ===========================< Data Loading >============================

DATASETS_DIR = Path(__file__).resolve().parents[3] / "datasets" / "json"


def load_all_cards() -> list[dict]:
    """datasets/json/ 하위의 모든 카드 JSON 파일을 로드하여 카드 단위로 정리합니다."""
    all_cards = []
    for company_dir in DATASETS_DIR.iterdir():
        if not company_dir.is_dir():
            continue
        for json_file in company_dir.glob("*.json"):
            data = json.loads(json_file.read_text(encoding="utf-8"))
            chunks = list(data.values())
            if not chunks:
                continue
            meta = chunks[0]
            all_cards.append({
                "card_name": meta.get("card_name"),
                "card_company": meta.get("card_company"),
                "annual_fee": meta.get("annual_fee", 0),
                "min_performance": meta.get("min_performance", 0),
                "major_categories": meta.get("major_categories", ""),
                "benefits_summary": meta.get("benefits_summary", ""),
                "chunks": chunks,
            })
    return all_cards


# ===========================< State >============================

class AgentState(TypedDict):
    messages: Annotated[List[AnyMessage], add_messages]
    # 구조화된 유저 입력
    total_budget: NotRequired[Optional[int]]
    category_spending: NotRequired[Optional[Dict[str, int]]]
    # 중간 결과
    filtered_cards: NotRequired[Optional[list]]
    calc_result_json: NotRequired[Optional[str]]
    # QA용 원본 데이터 보존
    last_raw_data: NotRequired[Optional[str]]


# ===========================< Nodes >============================

def filter_cards_node(state: AgentState):
    """전월실적 기준으로 카드를 필터링합니다."""
    print("[DEBUG] filter_cards_node")
    total_budget = state.get("total_budget", 0)

    all_cards = load_all_cards()
    filtered = [
        card for card in all_cards
        if card["min_performance"] <= total_budget
    ]

    print(f"  전체 {len(all_cards)}개 → 실적 충족 {len(filtered)}개")

    _test_log["filter"]["total_cards"] = len(all_cards)
    _test_log["filter"]["after_performance"] = len(filtered)

    if not filtered:
        return {
            "messages": [AIMessage(
                content=f"월 소비 {total_budget:,}원 기준으로 전월실적을 충족하는 카드가 없습니다."
            )],
            "filtered_cards": [],
        }

    return {"filtered_cards": filtered}


def calculate_discounts_node(state: AgentState):
    """LLM을 사용하여 각 카드의 카테고리별 예상 할인금액을 계산합니다."""
    print("[DEBUG] calculate_discounts_node")
    filtered_cards = state.get("filtered_cards", [])
    category_spending = state.get("category_spending", {})
    total_budget = state.get("total_budget", 0)

    if not filtered_cards:
        return {}

    # 유저가 선택한 카테고리와 major_categories가 겹치는 카드만 선별
    user_categories = set(category_spending.keys())
    relevant_cards = [
        card for card in filtered_cards
        if any(cat in card.get("major_categories", "") for cat in user_categories)
    ]

    if not relevant_cards:
        relevant_cards = filtered_cards[:10]

    print(f"  카테고리 매칭 후 카드 수: {len(relevant_cards)}개 (유저 카테고리: {user_categories})")
    _test_log["filter"]["after_category"] = len(relevant_cards)

    # 유저 소비 패턴 텍스트
    spending_lines = [f"월 총 소비: {total_budget:,}원"]
    for cat, amount in category_spending.items():
        spending_lines.append(f"- {cat}: 월 {amount:,}원")
    user_spending = "\n".join(spending_lines)

    # 카드 데이터 구성 (LLM에게 전달할 형태)
    cards_data = {}
    for card in relevant_cards:
        cards_data[card["card_name"]] = {
            "card_company": card["card_company"],
            "annual_fee": card["annual_fee"],
            "min_performance": card["min_performance"],
            "benefits": [
                {
                    "category": c.get("category", ""),
                    "content": c.get("content", ""),
                    "conditions": c.get("conditions", ""),
                }
                for c in card["chunks"]
            ],
        }

    print(f"  LLM에 전달할 카드 수: {len(cards_data)}")
    print(f"\n[DEBUG] user_spending:\n{user_spending}")
    print(f"\n[DEBUG] cards_data:\n{json.dumps(cards_data, ensure_ascii=False, indent=2)[:3000]}...")  # 앞 3000자만

    calc_prompt = CALC_PROMPT.format(
        user_spending=user_spending,
        cards_data=json.dumps(cards_data, ensure_ascii=False, indent=2),
    )

    llm_raw = llm.invoke([SystemMessage(content=calc_prompt)]).content
    llm_response = (
        llm_raw if isinstance(llm_raw, str)
        else json.dumps(llm_raw, ensure_ascii=False)
    )

    # 테스트 로그: calc 원본 저장
    try:
        _test_log["calc_raw"] = json.loads(
            llm_response.replace("```json", "").replace("```", "").strip()
        )
    except json.JSONDecodeError:
        _test_log["calc_raw"] = llm_response

    return {"calc_result_json": llm_response}


def rank_and_explain_node(state: AgentState):
    """계산 결과를 파싱하여 상위 3개 카드를 선정하고 추천 이유를 설명합니다."""
    print("[DEBUG] rank_and_explain_node")
    calc_json = state.get("calc_result_json", "")
    category_spending = state.get("category_spending", {})
    total_budget = state.get("total_budget", 0)

    # 1. 계산 결과 JSON 파싱
    try:
        cleaned = calc_json.replace("```json", "").replace("```", "").strip()
        calc_results: dict = json.loads(cleaned)
    except json.JSONDecodeError:
        print(f"[WARNING] 계산 결과 JSON 파싱 실패: {calc_json[:200]}")
        return {
            "messages": [AIMessage(content="계산 중 오류가 발생했습니다. 다시 시도해주세요.")]
        }

    # 2. details에서 월간 할인 합산 (코드 계산) → 정렬 → 상위 3개
    for card_data in calc_results.values():
        total_discount = sum(d.get("discount", 0) for d in card_data.get("details", []))
        card_data["total_discount"] = total_discount
        card_data["total_yearly_discount"] = total_discount * 12

    ranked = sorted(
        calc_results.items(),
        key=lambda x: x[1]["total_discount"],
        reverse=True,
    )[:3]

    top3 = {name: data for name, data in ranked}

    # 3. LLM에게 추천 설명 요청
    spending_lines = [f"월 총 소비: {total_budget:,}원"]
    for cat, amount in category_spending.items():
        spending_lines.append(f"- {cat}: 월 {amount:,}원")
    user_spending = "\n".join(spending_lines)

    explain_prompt = EXPLAIN_PROMPT.format(
        user_spending=user_spending,
        top3_cards=json.dumps(top3, ensure_ascii=False, indent=2),
    )

    explanation = llm.invoke([SystemMessage(content=explain_prompt)]).content

    # 테스트 로그: top3 + explain 원본 저장
    _test_log["top3"] = [{"card_name": name, **data} for name, data in ranked]
    _test_log["explain_raw"] = explanation if isinstance(explanation, str) else str(explanation)

    # 4. 최종 응답 구성
    response_parts = []
    for i, (name, data) in enumerate(ranked):
        rank_label = ["1순위", "2순위", "3순위"][i]
        total_disc = data.get("total_discount", 0)
        annual_fee = data.get("annual_fee", 0)
        net_benefit = (total_disc * 12) - annual_fee

        details_lines = []
        for d in data.get("details", []):
            if d.get("discount", 0) > 0:
                details_lines.append(
                    f"  - {d['category']}: {d['spending']:,}원 x {d['rate']} = {d['discount']:,}원"
                )

        card_section = f"[{rank_label}] {name} ({data.get('card_company', '')})\n"
        card_section += f"연회비: {annual_fee:,}원 | 월 예상 할인: {total_disc:,}원 | 연 순이익 추정: {net_benefit:,}원\n"
        if details_lines:
            card_section += "\n".join(details_lines) + "\n"

        response_parts.append(card_section)

    final_response = "\n".join(response_parts)
    final_response += f"\n{'=' * 40}\n{explanation}"

    return {
        "messages": [AIMessage(content=final_response)],
        "last_raw_data": json.dumps(top3, ensure_ascii=False),
    }


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
) -> Literal["calculate", "no_results"]:
    """필터링 결과가 있으면 계산 진행, 없으면 종료."""
    filtered = state.get("filtered_cards", [])
    return "calculate" if filtered else "no_results"


# ===========================< Graph Construction >============================

workflow = StateGraph(AgentState)

workflow.add_node("filter_cards", filter_cards_node)
workflow.add_node("calculate_discounts", calculate_discounts_node)
workflow.add_node("rank_and_explain", rank_and_explain_node)
workflow.add_node("answer_qa", answer_qa_node)

# 메인 흐름: filter → (결과 있으면) calculate → explain → END
workflow.add_edge(START, "filter_cards")
workflow.add_conditional_edges(
    "filter_cards",
    check_filter_result,
    {
        "calculate": "calculate_discounts",
        "no_results": END,
    },
)
workflow.add_edge("calculate_discounts", "rank_and_explain")
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
