"""
[실험 D] Compact Digest 기반 LLM 계획 생성 + 코드 전략 엔진 실행 방식

실험 C와 동일한 전략 엔진을 사용하되, LLM이 계산 계획을 생성할 때
구조화된 스키마 대신 Compact Digest(마크다운 요약)를 읽고 판단합니다.

흐름: 유저 입력 → LLM 필터링 → LLM이 Digest 기반 실행 계획 생성 → 코드 전략 엔진 → LLM 설명
실험 C 대비 차이: LLM Plan 프롬프트 입력이 구조화 스키마 → Compact Digest로 변경
"""

import os
import json
import time
import uuid

from datetime import datetime
from pathlib import Path
from typing import Annotated, Dict, List, Literal, Optional
from typing_extensions import NotRequired, TypedDict
from collections import defaultdict

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
from apps.backend.tools.Calc_tool import BenefitCalculator, DEFAULT_FUEL_PRICE_PER_LITER, INF, _pick, _effective_days

# ===========================< Setting >============================
load_dotenv(Path(__file__).resolve().parents[3] / ".env")

os.environ["LANGSMITH_TRACING_V2"] = "true"
os.environ["LANGSMITH_PROJECT"] = "Smart_Pick_Exp_D"
os.environ["LANGSMITH_ENDPOINT"] = "https://api.smith.langchain.com"

langfuse = Langfuse()

MODEL = "solar-pro2"
llm = init_chat_model(model=MODEL, temperature=0.0)

# ===========================< Test Log >============================
TEST_LOG_DIR = Path(__file__).resolve().parents[3] / "test_logs" / "exp_d"
PROMPT_VERSIONS = {"LLM_FILTER": "V1", "LLM_PLAN": "D_V1_DIGEST", "ENGINE": "StrategyEngine_V1", "EXPLAIN_PROMPT": "V3", "QA_PROMPT": "V1"}

_test_log: dict = {}


def _init_test_log(total_budget: int, category_spending: dict):
    global _test_log
    _test_log = {
        "timestamp": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "model": MODEL,
        "prompt_versions": PROMPT_VERSIONS,
        "experiment": "llm_plan_digest_strategy_engine",
        "input": {
            "total_budget": total_budget,
            "category_spending": category_spending,
        },
        "llm_filter_result": {},
        "llm_plans": [],
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
    print(f"\n[LOG] 실험D 로그 저장: {filepath}")


# ===========================< JSON Parser >============================

import re

def _parse_json_response(raw: str) -> dict | None:
    """LLM 응답에서 JSON을 추출합니다. 여러 패턴을 시도합니다."""
    # 1차: 코드블록 제거 후 시도
    cleaned = raw.replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # 2차: { ... } 블록을 정규식으로 추출
    match = re.search(r'\{[\s\S]*\}', raw)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    # 3차: 줄 단위로 JSON 시작/끝 찾기
    lines = raw.split("\n")
    json_lines = []
    in_json = False
    depth = 0
    for line in lines:
        if not in_json and "{" in line:
            in_json = True
            json_lines = []
        if in_json:
            json_lines.append(line)
            depth += line.count("{") - line.count("}")
            if depth <= 0:
                try:
                    return json.loads("\n".join(json_lines))
                except json.JSONDecodeError:
                    in_json = False
                    json_lines = []
                    depth = 0

    return None


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


# ===========================< Schema Adapter >============================
# exp_a와 동일: json_v2 → Master Schema v2 변환

def adapt_to_master_schema(card: dict) -> dict:
    """json_v2 카드 데이터를 BenefitCalculator가 기대하는 Master Schema v2로 변환합니다."""
    benefits_v2 = []
    for i, b in enumerate(card.get("benefits", [])):
        rate = b.get("rate") or 0
        monthly_limit = b.get("monthly_limit")

        if rate > 0:
            calc_method = "RATE"
        else:
            calc_method = "RATE"

        benefits_v2.append({
            "benefit_id": f"b_{i}",
            "category": b.get("category", ""),
            "content": b.get("content", ""),
            "frequency": "MONTHLY",
            "reward_type": b.get("benefit_type", "discount").upper(),
            "reward_unit": {"currency": "KRW", "currency_to_krw_rate": 1.0},
            "tier_conditions": [],
            "calculation_rule": {
                "calc_method": calc_method,
                "rate": rate,
                "fixed_amount": None,
                "unit_label": None,
                "unit_amount": None,
                "monthly_limit": monthly_limit,
                "monthly_usage_limit": None,
                "fallback_reward_rate": 0.0,
                "transaction_tiers": None,
            },
            "transaction_conditions": {
                "min_payment_amount": 0,
                "max_payment_amount_applied": None,
                "max_count_per_day": None,
                "max_count_per_month": None,
                "max_count_per_year": None,
                "day_of_week": None,
                "time_of_day": {"start": None, "end": None},
                "requires_auto_payment": False,
                "requires_offline": False,
                "requires_online": False,
            },
            "group_id": None,
            "ui_warnings": [],
            "edge_case_flags": {
                "requires_user_selection": False,
                "excludes_from_performance": False,
                "category_excludes_from_performance": False,
                "special_month_bonus": {"type": None, "multiplier": None, "bonus_limit_add": None, "months": None},
                "performance_gap_forgiveness": {"enabled": False, "max_gap_amount": None, "max_count_per_year": None},
                "current_month_performance": False,
                "payment_platform_bonus": {"platform": None, "additional_rate": None},
                "annual_usage_tiers": [],
                "annual_voucher": {"voucher_value_krw": None, "initial_year_condition": None, "renewal_year_condition": None, "choices": None},
                "escape_hatch_note": None,
            },
        })

    return {
        "card_meta": {
            "card_id": card.get("_file_stem", ""),
            "card_name": card.get("card_name", ""),
            "card_company": card.get("card_company", ""),
            "annual_fee_domestic": card.get("annual_fee", 0),
            "annual_fee_international": None,
            "minimum_performance": card.get("minimum_performance", 0),
            "performance_excluded_categories": None,
        },
        "benefit_groups": [],
        "benefits": benefits_v2,
    }


# ===========================< Strategy Engine >============================
# BenefitCalculator의 개별 메서드를 전략 단위로 분해하여 LLM 계획에 따라 선택 실행

STRATEGY_CATALOG = [
    "PERFORMANCE_CHECK", "TIER_SELECTION",
    "RATE_CALC", "FIXED_CALC", "PER_UNIT_CALC",
    "TRANSACTION_LIMIT_APPLY", "MONTHLY_LIMIT_APPLY", "FALLBACK_APPLY",
    "GROUP_LIMIT_APPLY", "WATERFALL_APPLY", "ANNUAL_SPECIALS", "ALL_DOMESTIC_SWEEP",
]


class StrategyEngine:
    """LLM이 생성한 실행 계획에 따라 BenefitCalculator의 로직을 전략 단위로 실행합니다."""

    def __init__(self, card_data: dict):
        self.card_data = card_data
        self.meta = card_data.get("card_meta", {})
        self.groups = {g["group_id"]: g for g in card_data.get("benefit_groups", [])}
        self.benefits = card_data.get("benefits", [])
        self._perf_excluded_cats: set[str] = set(self.meta.get("performance_excluded_categories") or [])

    def execute(
        self,
        plan: dict,
        user_budgets: dict[str, int],
        user_total_spend: int,
    ) -> dict:
        """
        LLM 생성 계획을 받아 지정된 전략만 실행합니다.

        Args:
            plan: LLM이 생성한 실행 계획 JSON
                  {"pipeline": [...], "benefit_strategies": {"b_id": [...], ...}}
            user_budgets: 카테고리 → 월 예산 매핑
            user_total_spend: 전체 월 소비액
        """
        pipeline = plan.get("pipeline", [])
        benefit_strategies = plan.get("benefit_strategies", {})

        result = {
            "card_name": self.meta.get("card_name"),
            "card_id": self.meta.get("card_id"),
            "performance_met": True,
            "adjusted_performance": user_total_spend,
            "monthly_total_krw": 0,
            "annual_total_krw": 0,
            "category_breakdown": [],
            "annual_breakdown": [],
            "warnings": [],
            "executed_strategies": {"pipeline": pipeline, "benefit_strategies": benefit_strategies},
        }

        # ── Pipeline 전략 실행 ──
        performance = user_total_spend
        if "PERFORMANCE_CHECK" in pipeline:
            performance = self._strategy_performance_check(user_budgets, user_total_spend)
            min_perf = self.meta.get("minimum_performance", 0)
            result["adjusted_performance"] = performance
            result["performance_met"] = performance >= min_perf

            if not result["performance_met"]:
                # 채워드림 확인
                gap_applied = False
                for b in self.benefits:
                    fg = (b.get("edge_case_flags") or {}).get("performance_gap_forgiveness") or {}
                    if fg.get("enabled") and (min_perf - performance) <= (fg.get("max_gap_amount") or 0):
                        result["performance_met"] = True
                        gap_applied = True
                        break
                if gap_applied:
                    result["warnings"].append("전월실적 채워드림 적용 (연 횟수 제한 있음)")
                else:
                    result["warnings"].append(
                        f"보정된 전월 실적({performance:,.0f}원)이 최소 조건({min_perf:,.0f}원)에 미달합니다."
                    )
                    return result

        # ── 혜택별 전략 실행 ──
        # All_Domestic을 마지막에 처리 (WATERFALL용)
        do_waterfall = "WATERFALL_APPLY" in pipeline
        do_all_domestic_sweep = "ALL_DOMESTIC_SWEEP" in pipeline

        sorted_benefits = sorted(
            self.benefits,
            key=lambda x: (
                1 if x.get("category") == "All_Domestic" else 0,
                x.get("benefit_id", ""),
            ),
        )

        remaining_total = user_total_spend
        monthly_results: list[dict] = []
        quarterly_results: list[dict] = []
        annual_freq_results: list[dict] = []

        for b in sorted_benefits:
            bid = b.get("benefit_id", "")
            cat = b.get("category")
            freq = b.get("frequency", "MONTHLY")
            strategies = benefit_strategies.get(bid, [])

            # All_Domestic sweep 처리
            if cat == "All_Domestic":
                if not do_all_domestic_sweep and "ALL_DOMESTIC_SWEEP" not in strategies:
                    continue
                budget = remaining_total if do_waterfall else user_total_spend
            else:
                budget = user_budgets.get(cat, 0)

            if budget <= 0 and freq not in ("ANNUAL", "ONCE"):
                continue

            # 혜택별 전략이 없으면 스킵
            if not strategies and bid not in benefit_strategies:
                # pipeline에 BENEFIT_LOOP가 있으면 기본 전략으로 실행
                if "BENEFIT_LOOP" not in pipeline:
                    continue

            calc_result = self._execute_benefit_strategies(
                benefit=b,
                strategies=strategies,
                budget=budget,
                performance=performance,
                user_total_spend=user_total_spend,
                pipeline=pipeline,
            )

            if calc_result["amount_krw"] <= 0:
                continue

            # Waterfall: 사용된 예산 차감
            if do_waterfall and cat != "All_Domestic" and calc_result["used_budget"] > 0:
                remaining_total -= calc_result["used_budget"]
                remaining_total = max(remaining_total, 0)

            if freq == "MONTHLY":
                monthly_results.append(calc_result)
            elif freq == "QUARTERLY":
                quarterly_results.append(calc_result)
            elif freq in ("ANNUAL", "ONCE"):
                annual_freq_results.append(calc_result)

        # ── 그룹 한도 ──
        if "GROUP_LIMIT_APPLY" in pipeline or "GROUP_LIMIT" in pipeline:
            self._strategy_group_limit(monthly_results)

        # ── 카테고리별 합산 ──
        cat_totals: dict[str, dict] = defaultdict(lambda: {"monthly_discount_krw": 0, "warnings": []})
        for r in monthly_results:
            cat = r["category"]
            cat_totals[cat]["monthly_discount_krw"] += r["amount_krw"]
            cat_totals[cat]["warnings"].extend(r["warnings"])

        for cat, data in cat_totals.items():
            result["category_breakdown"].append({
                "category": cat,
                "monthly_discount_krw": round(data["monthly_discount_krw"]),
                "warnings": list(set(data["warnings"])),
            })

        result["category_breakdown"].sort(key=lambda x: (x["category"] == "All_Domestic", x["category"]))
        result["monthly_total_krw"] = round(sum(r["amount_krw"] for r in monthly_results))

        # ── 연간 혜택 ──
        quarterly_annual = sum(r["amount_krw"] * 4 for r in quarterly_results)
        annual_freq_total = sum(r["amount_krw"] for r in annual_freq_results)
        annual_special_total = 0

        if "ANNUAL_SPECIALS" in pipeline:
            annual_specials = self._strategy_annual_specials(user_total_spend)
            annual_special_total = sum(a["amount_krw"] for a in annual_specials)
            result["annual_breakdown"].extend(annual_specials)

        result["annual_total_krw"] = round(annual_freq_total + quarterly_annual + annual_special_total)
        result["annual_breakdown"] = [
            {"category": r["category"], "amount_krw": r["amount_krw"], "frequency": r["frequency"]}
            for r in annual_freq_results + quarterly_results
        ] + result["annual_breakdown"]

        return result

    # ── 개별 전략 구현 ──

    def _strategy_performance_check(self, user_budgets: dict[str, int], user_total_spend: int) -> int:
        """PERFORMANCE_CHECK: 전월 실적 보정 (BenefitCalculator._adjusted_performance 동일)"""
        adjusted = user_total_spend
        for cat in self._perf_excluded_cats:
            adjusted -= user_budgets.get(cat, 0)
        already_excluded = set(self._perf_excluded_cats)
        for b in self.benefits:
            flags = b.get("edge_case_flags") or {}
            cat = b.get("category")
            if cat and cat not in already_excluded:
                if flags.get("excludes_from_performance") or flags.get("category_excludes_from_performance"):
                    adjusted -= user_budgets.get(cat, 0)
                    already_excluded.add(cat)
        return max(adjusted, 0)

    def _strategy_tier_selection(self, benefit: dict, performance: float) -> dict | None:
        """TIER_SELECTION: 실적 구간 매칭 (BenefitCalculator._find_best_tier 동일)"""
        tier_conditions = benefit.get("tier_conditions") or []
        edge_flags = benefit.get("edge_case_flags") or {}
        perf_for_tier = performance
        if edge_flags.get("current_month_performance", False):
            perf_for_tier = performance  # 당월 기준은 execute에서 user_total_spend 전달
        return BenefitCalculator._find_best_tier(tier_conditions, perf_for_tier)

    def _execute_benefit_strategies(
        self,
        benefit: dict,
        strategies: list[str],
        budget: float,
        performance: float,
        user_total_spend: float,
        pipeline: list[str],
    ) -> dict:
        """혜택별 지정된 전략 리스트를 순차 실행하여 최종 금액을 산출합니다."""
        calc_rule = benefit.get("calculation_rule") or {}
        trans_cond = benefit.get("transaction_conditions") or {}
        edge_flags = benefit.get("edge_case_flags") or {}
        reward_unit = benefit.get("reward_unit") or {}
        freq = benefit.get("frequency", "MONTHLY")

        conversion_rate = reward_unit.get("currency_to_krw_rate", 1.0)
        warnings: list[str] = list(benefit.get("ui_warnings") or [])

        # Tier 결정
        tier = None
        if "TIER_SELECTION" in strategies or "TIER_SELECTION" in pipeline:
            perf_for_tier = performance
            if edge_flags.get("current_month_performance", False):
                perf_for_tier = user_total_spend
            tier = BenefitCalculator._find_best_tier(benefit.get("tier_conditions") or [], perf_for_tier)

        # 변수 확정
        rate = _pick(tier, "rate", calc_rule.get("rate")) or 0.0
        fixed_amount = _pick(tier, "fixed_amount", calc_rule.get("fixed_amount")) or 0
        unit_amount = _pick(tier, "unit_amount", calc_rule.get("unit_amount")) or 0
        monthly_limit = _pick(tier, "monthly_limit", calc_rule.get("monthly_limit")) or INF
        monthly_usage_limit = _pick(tier, "monthly_usage_limit", calc_rule.get("monthly_usage_limit")) or INF
        fallback_rate = calc_rule.get("fallback_reward_rate") or 0.0

        # Transaction conditions
        min_payment = trans_cond.get("min_payment_amount") or 0
        max_payment_applied = trans_cond.get("max_payment_amount_applied") or INF
        max_count_day = trans_cond.get("max_count_per_day") or INF
        max_count_month = trans_cond.get("max_count_per_month") or INF
        day_of_week = trans_cond.get("day_of_week")

        eff_days = _effective_days(day_of_week)
        max_monthly_txns = min(max_count_month, max_count_day * eff_days)

        # Platform bonus
        platform_bonus = edge_flags.get("payment_platform_bonus") or {}
        add_rate = platform_bonus.get("additional_rate") or 0.0

        # Transaction limit 적용
        eff_budget = budget
        if "TRANSACTION_LIMIT_APPLY" in strategies:
            eff_budget = min(budget, monthly_usage_limit)
            if eff_budget < min_payment and freq not in ("ANNUAL", "ONCE", "QUARTERLY"):
                return self._empty_record(benefit)

        # 계산 방법 실행
        calc_method = calc_rule.get("calc_method", "RATE")
        raw_amount = 0.0
        used_budget = 0.0

        if "RATE_CALC" in strategies and calc_method == "RATE":
            total_rate = rate + add_rate
            cap = max_payment_applied * max_monthly_txns
            eff = min(eff_budget, cap)
            raw_amount = eff * total_rate
            used_budget = eff

        elif "FIXED_CALC" in strategies and calc_method == "FIXED_AMOUNT":
            if max_monthly_txns >= INF and max_count_month >= INF:
                raw_amount = fixed_amount
            else:
                possible = eff_budget // max(min_payment, 1) if min_payment > 0 else max_monthly_txns
                count = min(max_monthly_txns, possible)
                raw_amount = fixed_amount * count
            used_budget = eff_budget

        elif "PER_UNIT_CALC" in strategies and calc_method == "PER_UNIT":
            label = calc_rule.get("unit_label", "")
            if label == "liter":
                liters = eff_budget / DEFAULT_FUEL_PRICE_PER_LITER
                raw_amount = liters * unit_amount
                warnings.append(f"주유 할인은 기준유가 {DEFAULT_FUEL_PRICE_PER_LITER:,}원/L 기반 추정치입니다")
            elif label == "transaction":
                possible = eff_budget // max(min_payment, 1) if min_payment > 0 else max_monthly_txns
                count = min(max_monthly_txns, possible)
                raw_amount = unit_amount * count
            else:
                raw_amount = unit_amount
            used_budget = eff_budget

        else:
            # 전략에 명시된 calc이 없으면 calc_method 기반 자동 실행
            if calc_method == "RATE":
                total_rate = rate + add_rate
                cap = max_payment_applied * max_monthly_txns
                eff = min(eff_budget, cap)
                raw_amount = eff * total_rate
                used_budget = eff
            elif calc_method == "FIXED_AMOUNT":
                if max_monthly_txns >= INF and max_count_month >= INF:
                    raw_amount = fixed_amount
                else:
                    possible = eff_budget // max(min_payment, 1) if min_payment > 0 else max_monthly_txns
                    count = min(max_monthly_txns, possible)
                    raw_amount = fixed_amount * count
                used_budget = eff_budget
            elif calc_method == "PER_UNIT":
                label = calc_rule.get("unit_label", "")
                if label == "liter":
                    liters = eff_budget / DEFAULT_FUEL_PRICE_PER_LITER
                    raw_amount = liters * unit_amount
                elif label == "transaction":
                    possible = eff_budget // max(min_payment, 1) if min_payment > 0 else max_monthly_txns
                    count = min(max_monthly_txns, possible)
                    raw_amount = unit_amount * count
                else:
                    raw_amount = unit_amount
                used_budget = eff_budget
            elif calc_method == "TIERED_RATE_BY_TRANSACTION":
                txn_tiers = calc_rule.get("transaction_tiers") or []
                if txn_tiers:
                    best = max(txn_tiers, key=lambda t: t.get("rate", 0))
                    raw_amount = eff_budget * (best["rate"] + add_rate)
                used_budget = eff_budget
            elif calc_method == "MAX_COVER_UP_TO_LIMIT":
                raw_amount = min(eff_budget, monthly_limit)
                used_budget = raw_amount

        # Monthly limit 적용
        final_amount = raw_amount
        if "MONTHLY_LIMIT_APPLY" in strategies:
            final_amount = min(raw_amount, monthly_limit)

            # Fallback 적용
            if "FALLBACK_APPLY" in strategies and raw_amount > monthly_limit and fallback_rate > 0 and (rate + add_rate) > 0:
                consumed = monthly_limit / (rate + add_rate)
                remaining = used_budget - consumed
                if remaining > 0:
                    final_amount += remaining * fallback_rate
        else:
            final_amount = min(raw_amount, monthly_limit)

        # KRW 환산
        krw = final_amount * conversion_rate

        # 경고
        time_of_day = trans_cond.get("time_of_day") or {}
        if time_of_day.get("start"):
            warnings.append(f"시간대 한정: {time_of_day['start']}~{time_of_day['end']}")
        if day_of_week:
            warnings.append(f"요일 한정: {', '.join(day_of_week)}")
        if trans_cond.get("requires_auto_payment"):
            warnings.append("자동납부(정기결제) 필수")

        return {
            "benefit_id": benefit.get("benefit_id"),
            "category": benefit.get("category"),
            "frequency": freq,
            "reward_type": benefit.get("reward_type"),
            "raw_amount": round(final_amount, 2),
            "amount_krw": round(krw),
            "used_budget": round(used_budget),
            "group_id": benefit.get("group_id"),
            "warnings": warnings,
        }

    def _strategy_group_limit(self, results: list[dict]) -> None:
        """GROUP_LIMIT_APPLY: 그룹 한도 적용 (BenefitCalculator._apply_group_limits 동일)"""
        buckets: dict[str, list[dict]] = defaultdict(list)
        for r in results:
            gid = r.get("group_id")
            if gid:
                buckets[gid].append(r)

        for gid, items in buckets.items():
            group_info = self.groups.get(gid)
            if not group_info:
                continue
            g_type = group_info.get("group_type", "SHARED_LIMIT")
            g_limit = group_info.get("limit_amount") or INF

            if g_type == "SHARED_LIMIT":
                total = sum(r["amount_krw"] for r in items)
                if total > g_limit:
                    ratio = g_limit / total
                    for r in items:
                        r["amount_krw"] = round(r["amount_krw"] * ratio)
            elif g_type == "USER_CHOICE_ONE":
                best = max(items, key=lambda r: r["amount_krw"])
                for r in items:
                    if r["benefit_id"] != best["benefit_id"]:
                        r["amount_krw"] = 0
                        r["warnings"].append("그룹 내 택1 조건으로 인해 제외됨")
            elif g_type == "AUTO_TOP_N":
                n = group_info.get("top_n_count") or 1
                ranked = sorted(items, key=lambda r: r["amount_krw"], reverse=True)
                selected_ids = {r["benefit_id"] for r in ranked[:n]}
                for r in items:
                    if r["benefit_id"] not in selected_ids:
                        r["amount_krw"] = 0
                        r["warnings"].append(f"AUTO_TOP_{n} 미선택으로 제외됨")
                selected_total = sum(r["amount_krw"] for r in items)
                if selected_total > g_limit:
                    ratio = g_limit / selected_total
                    for r in items:
                        if r["amount_krw"] > 0:
                            r["amount_krw"] = round(r["amount_krw"] * ratio)

    def _strategy_annual_specials(self, user_total_spend: float) -> list[dict]:
        """ANNUAL_SPECIALS: 연간 특수 혜택 (BenefitCalculator._calc_annual_specials 동일)"""
        items: list[dict] = []
        annual_projection = user_total_spend * 12
        for b in self.benefits:
            flags = b.get("edge_case_flags") or {}
            for at in flags.get("annual_usage_tiers") or []:
                min_spend = at.get("min_annual_spend", 0)
                max_spend = at.get("max_annual_spend") or INF
                cashback = at.get("cashback_amount", 0)
                if annual_projection >= min_spend and min_spend > 0:
                    eligible = min(annual_projection, max_spend)
                    times = int(eligible // min_spend)
                    items.append({
                        "benefit_id": b.get("benefit_id"),
                        "category": b.get("category"),
                        "type": "annual_cashback",
                        "amount_krw": cashback * times,
                        "description": at.get("description", ""),
                    })
            voucher = flags.get("annual_voucher") or {}
            val = voucher.get("voucher_value_krw")
            if val:
                items.append({
                    "benefit_id": b.get("benefit_id"),
                    "category": b.get("category"),
                    "type": "voucher",
                    "amount_krw": val,
                    "description": voucher.get("initial_year_condition", ""),
                    "choices": voucher.get("choices"),
                })
        return items

    @staticmethod
    def _empty_record(benefit: dict) -> dict:
        return {
            "benefit_id": benefit.get("benefit_id"),
            "category": benefit.get("category"),
            "frequency": benefit.get("frequency", "MONTHLY"),
            "reward_type": benefit.get("reward_type"),
            "raw_amount": 0,
            "amount_krw": 0,
            "used_budget": 0,
            "group_id": benefit.get("group_id"),
            "warnings": [],
        }


# ===========================< LLM Prompts >============================

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


LLM_PLAN_PROMPT_D_V1 = """
너는 신용카드 혜택 계산을 위한 '실행 계획 생성기'다.
카드의 혜택 요약(Compact Digest)을 읽고, 정확한 계산을 위해 어떤 전략을 어떤 순서로 실행해야 하는지 JSON 계획을 생성한다.

[유저 소비 패턴]
월 총 소비: {total_budget:,}원
카테고리별 소비:
{spending_lines}

[카드 혜택 요약 (Compact Digest)]
{card_digest}

[혜택 ID 매핑]
{benefit_id_map}

[사용 가능한 전략 카탈로그]
- PERFORMANCE_CHECK: 전월실적 보정 (실적 제외 카테고리 반영)
- TIER_SELECTION: 전월실적 구간별 혜택 매칭 (예: "30만 이상 5%, 60만 이상 7%")
- RATE_CALC: 정률 할인/적립 계산 (예: "5% 할인", "1% 적립")
- FIXED_CALC: 정액 할인 계산 (예: "건당 300원", "월 3,000원 할인")
- PER_UNIT_CALC: 단위당 할인 계산 (예: "리터당 60원 할인")
- TRANSACTION_LIMIT_APPLY: 거래 조건 적용 (예: "1일 1회, 월 2회", "건당 5만원 이상")
- MONTHLY_LIMIT_APPLY: 월 한도 적용 (예: "월 할인 한도 30,000원")
- FALLBACK_APPLY: 한도 초과 시 기본 적립률 적용 (예: "한도 초과 시 0.1% 적립")
- GROUP_LIMIT_APPLY: 그룹 통합 한도 적용 (예: "[통합한도 공유]")
- WATERFALL_APPLY: 카테고리별 소비 차감 후 잔여액으로 전체 혜택 적용
- ANNUAL_SPECIALS: 연간 캐시백/바우처 혜택 산출 (예: "연간 500만 사용 시 2만원 캐시백")
- ALL_DOMESTIC_SWEEP: 전 가맹점(All_Domestic) 혜택을 잔여 소비액에 적용 (예: "전 가맹점 1% 적립")

[작업]
위 Compact Digest를 읽고, 유저의 소비 패턴에 맞는 최적의 실행 계획을 JSON으로 생성하라.

[분석 규칙]
1. pipeline: 카드 전체에 적용할 전략 (순서대로 실행)
   - 전월실적 조건이 있으면 PERFORMANCE_CHECK 필수
   - "실적구간별" 또는 구간별 할인율/혜택이 다르면 TIER_SELECTION 추가
   - 혜택이 여러 개면 BENEFIT_LOOP 추가
   - "[통합한도 공유]" 또는 공유 한도 언급이 있으면 GROUP_LIMIT 추가
   - "전 가맹점" 혜택이 있고 다른 카테고리 혜택도 있으면 WATERFALL_APPLY 추가
   - 연간 캐시백/바우처 혜택이 있으면 ANNUAL_SPECIALS 추가
2. benefit_strategies: 각 혜택(benefit_id)별로 적용할 전략 리스트
   - "X% 할인/적립" → RATE_CALC
   - "건당 X원", "월 X원 할인" 같은 정액 → FIXED_CALC
   - "리터당 X원" 같은 단위당 할인 → PER_UNIT_CALC
   - "월 한도 X원" 언급 → MONTHLY_LIMIT_APPLY 추가
   - "한도 초과 시 X% 적립" 언급 → FALLBACK_APPLY 추가
   - "1일 1회", "월 N회", "건당 X원 이상" 같은 거래 조건 → TRANSACTION_LIMIT_APPLY 추가
   - 유저 소비 카테고리와 완전히 무관한 혜택의 benefit_id는 포함하지 말 것
   - 단, "General", "All_Domestic", "전 가맹점" 카테고리 혜택은 유저의 모든 소비에 적용되므로 반드시 포함할 것
   - 카테고리 포함 관계를 고려할 것: Coffee는 Food에 포함될 수 있고, 주유/교통은 Traffic에 해당하며, 편의점/마트는 Shopping에 해당함
   - [혜택 ID 매핑]의 benefit_id를 그대로 사용할 것

[출력 형식] 반드시 아래 JSON 포맷만 출력하세요. 마크다운이나 설명 없이 JSON만.
{{
    "pipeline": ["PERFORMANCE_CHECK", "TIER_SELECTION", ...],
    "benefit_strategies": {{
        "b_0": ["RATE_CALC", "MONTHLY_LIMIT_APPLY", "FALLBACK_APPLY"],
        "b_1": ["PER_UNIT_CALC"],
        "b_2": ["RATE_CALC", "ALL_DOMESTIC_SWEEP"]
    }}
}}
"""


# ===========================< State >============================

class AgentState(TypedDict):
    messages: Annotated[List[AnyMessage], add_messages]
    total_budget: NotRequired[Optional[int]]
    category_spending: NotRequired[Optional[Dict[str, int]]]
    # 중간 결과
    all_cards: NotRequired[Optional[list]]
    shortlist_cards: NotRequired[Optional[list]]
    llm_plans: NotRequired[Optional[list]]
    calc_results: NotRequired[Optional[list]]
    llm_filter_raw: NotRequired[Optional[str]]
    # 최종 결과
    recommended_cards: NotRequired[Optional[list]]
    last_raw_data: NotRequired[Optional[str]]


# ===========================< Nodes >============================

@observe(name="exp_d_llm_filter")
@traceable(run_type="chain", name="exp_d_llm_filter")
def llm_filter_node(state: AgentState):
    """LLM이 직접 카드를 필터링하고 Top 7을 선정합니다."""
    _node_start = time.time()
    print("[EXP-D] llm_filter_node")
    total_budget = state.get("total_budget", 0)
    category_spending = state.get("category_spending", {})

    all_cards = load_all_cards()

    cards_summary_lines = []
    for i, card in enumerate(all_cards):
        categories = card.get("card_categories", [])
        benefits_preview = []
        for b in card.get("benefits", [])[:3]:
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

    result = _parse_json_response(raw_response)
    if result:
        selected = result.get("selected_cards", [])
    else:
        print(f"  [WARN] LLM JSON 파싱 실패")
        selected = []

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
        print(f"    {i+1}. {card['card_name']} (relevance={card.get('_llm_relevance', 'N/A')})")

    _test_log["llm_filter_result"] = {
        "total_cards": len(all_cards),
        "selected_count": len(shortlist),
        "selected": [
            {"card_name": c["card_name"], "reason": c.get("_llm_reason", ""), "relevance_score": c.get("_llm_relevance", 0)}
            for c in shortlist
        ],
        "elapsed_seconds": round(time.time() - _node_start, 2),
    }
    print(f"  [TIME] llm_filter: {_test_log['llm_filter_result']['elapsed_seconds']}초")

    if not shortlist:
        return {
            "messages": [AIMessage(content=f"월 소비 {total_budget:,}원 기준으로 적합한 카드를 찾지 못했습니다.")],
            "shortlist_cards": [],
            "all_cards": all_cards,
            "llm_filter_raw": raw_response,
        }

    return {
        "shortlist_cards": shortlist,
        "all_cards": all_cards,
        "llm_filter_raw": raw_response,
    }


@observe(name="exp_d_llm_plan")
@traceable(run_type="chain", name="exp_d_llm_plan")
def llm_plan_node(state: AgentState):
    """LLM이 Compact Digest를 읽고 각 카드별 실행 계획(JSON)을 생성합니다."""
    _node_start = time.time()
    print("[EXP-D] llm_plan_node (Digest 기반)")
    shortlist = state.get("shortlist_cards", [])
    category_spending = state.get("category_spending", {})
    total_budget = state.get("total_budget", 0)

    spending_lines = "\n".join(
        f"- {cat}: 월 {amt:,}원" for cat, amt in category_spending.items()
    )

    llm_plans = []
    for card in shortlist:
        master_data = adapt_to_master_schema(card)

        # Compact Digest 로드
        card_digest = load_digest(card)

        # benefit_id ↔ category 매핑 (LLM이 benefit_id를 알 수 있도록)
        id_map_lines = []
        for b in master_data["benefits"]:
            id_map_lines.append(f"  - {b['benefit_id']}: {b['category']} ({b.get('content', '')})")

        prompt = LLM_PLAN_PROMPT_D_V1.format(
            total_budget=total_budget,
            spending_lines=spending_lines,
            card_digest=card_digest,
            benefit_id_map="\n".join(id_map_lines),
        )

        response = llm.invoke([SystemMessage(content=prompt)])
        raw = response.content if isinstance(response.content, str) else str(response.content)

        plan = _parse_json_response(raw)
        if plan is None:
            print(f"  [WARN] {card['card_name']} 계획 JSON 파싱 실패, 기본 계획 사용")
            print(f"  [DEBUG] raw 응답 앞 200자: {raw[:200]}")
            plan = {
                "pipeline": ["PERFORMANCE_CHECK", "BENEFIT_LOOP"],
                "benefit_strategies": {
                    b["benefit_id"]: ["RATE_CALC", "MONTHLY_LIMIT_APPLY"]
                    for b in master_data["benefits"]
                    if b.get("category") in category_spending or b.get("category") == "All_Domestic"
                },
            }

        # benefit_strategies가 비어있으면 fallback 자동 생성
        if not plan.get("benefit_strategies"):
            print(f"  [FALLBACK] {card['card_name']}: benefit_strategies 비어있음 → 자동 생성")
            GENERAL_CATS = {"General", "All_Domestic"}
            plan["benefit_strategies"] = {
                b["benefit_id"]: ["RATE_CALC", "MONTHLY_LIMIT_APPLY"]
                for b in master_data["benefits"]
                if b.get("category") in category_spending or b.get("category") in GENERAL_CATS
            }

        llm_plans.append({
            "card_name": card.get("card_name"),
            "plan": plan,
            "plan_raw": raw,
            "_card_data": card,
            "_master_data": master_data,
        })

        pipeline_str = ", ".join(plan.get("pipeline", []))
        n_benefits = len(plan.get("benefit_strategies", {}))
        print(f"  {card['card_name']}: pipeline=[{pipeline_str}] benefits={n_benefits}개")

    _plan_elapsed = round(time.time() - _node_start, 2)
    _test_log["llm_plans"] = [
        {
            "card_name": p["card_name"],
            "plan": p["plan"],
        }
        for p in llm_plans
    ]
    _test_log["plan_elapsed_seconds"] = _plan_elapsed
    print(f"  [TIME] llm_plan: {_plan_elapsed}초")

    return {"llm_plans": llm_plans}


@observe(name="exp_d_strategy_engine")
@traceable(run_type="chain", name="exp_d_strategy_engine")
def strategy_engine_node(state: AgentState):
    """LLM 계획에 따라 StrategyEngine이 선택적으로 전략을 실행합니다."""
    _node_start = time.time()
    print("[EXP-D] strategy_engine_node")
    llm_plans = state.get("llm_plans", [])
    category_spending = state.get("category_spending", {})
    total_budget = state.get("total_budget", 0)

    calc_results = []
    for plan_item in llm_plans:
        card = plan_item["_card_data"]
        master_data = plan_item["_master_data"]
        plan = plan_item["plan"]

        engine = StrategyEngine(master_data)
        result = engine.execute(
            plan=plan,
            user_budgets=category_spending,
            user_total_spend=total_budget,
        )

        monthly = result.get("monthly_total_krw", 0)
        annual = result.get("annual_total_krw", 0)
        yearly_from_monthly = monthly * 12

        calc_results.append({
            "card_name": card.get("card_name"),
            "card_company": card.get("card_company"),
            "annual_fee": card.get("annual_fee", 0),
            "minimum_performance": card.get("minimum_performance", 0),
            "performance_met": result.get("performance_met", False),
            "expected_monthly_benefit": monthly,
            "expected_yearly_benefit": yearly_from_monthly + annual,
            "category_breakdown": result.get("category_breakdown", []),
            "annual_breakdown": result.get("annual_breakdown", []),
            "calc_warnings": result.get("warnings", []),
            "executed_strategies": result.get("executed_strategies", {}),
            "unclear_benefits": card.get("unclear_benefits", []),
            "_llm_reason": card.get("_llm_reason", ""),
            "_llm_relevance": card.get("_llm_relevance", 0),
            "_digest_path": card.get("_digest_path", ""),
            "_card_data": card,
        })

        status = "OK" if result.get("performance_met") else "실적미달"
        print(f"  {card['card_name']}: 월 {monthly:,}원 [{status}]")

    _engine_elapsed = round(time.time() - _node_start, 2)
    _test_log["calc_results"] = [
        {
            "card_name": r["card_name"],
            "performance_met": r["performance_met"],
            "expected_monthly_benefit": r["expected_monthly_benefit"],
            "category_breakdown": r["category_breakdown"],
            "calc_warnings": r["calc_warnings"],
            "executed_strategies": r["executed_strategies"],
            "llm_reason": r["_llm_reason"],
        }
        for r in calc_results
    ]
    _test_log["engine_elapsed_seconds"] = _engine_elapsed
    print(f"  [TIME] strategy_engine: {_engine_elapsed}초")

    return {"calc_results": calc_results}


@observe(name="exp_d_rank_and_explain")
def rank_and_explain_node(state: AgentState):
    """최종 랭킹 후 LLM 추천 설명을 생성합니다."""
    _node_start = time.time()
    print("[EXP-D] rank_and_explain_node")
    calc_results = state.get("calc_results", [])
    category_spending = state.get("category_spending", {})
    total_budget = state.get("total_budget", 0)

    if not calc_results:
        return {"messages": [AIMessage(content="혜택 계산 결과가 없습니다.")]}

    met_cards = [c for c in calc_results if c.get("performance_met", True)]
    if not met_cards:
        met_cards = calc_results

    ranked = sorted(met_cards, key=lambda x: x["expected_monthly_benefit"], reverse=True)[:3]

    spending_lines = [f"월 총 소비: {total_budget:,}원"]
    for cat, amount in category_spending.items():
        spending_lines.append(f"- {cat}: 월 {amount:,}원")
    user_spending = "\n".join(spending_lines)

    top1 = ranked[0]
    card_digest = load_digest(top1.get("_card_data", {}))

    breakdown_lines = []
    for cb in top1.get("category_breakdown", []):
        breakdown_lines.append(f"  - {cb['category']}: {cb['monthly_discount_krw']:,}원")
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

    _test_log["top3"] = [
        {
            "card_name": r["card_name"],
            "expected_monthly_benefit": r["expected_monthly_benefit"],
            "category_breakdown": r.get("category_breakdown", []),
            "llm_reason": r.get("_llm_reason", ""),
        }
        for r in ranked
    ]
    _test_log["explain_raw"] = explanation if isinstance(explanation, str) else str(explanation)

    response_parts = []
    for i, card in enumerate(ranked):
        rank_label = ["1순위", "2순위", "3순위"][i]
        monthly = card["expected_monthly_benefit"]
        yearly = card["expected_yearly_benefit"]
        annual_fee = card["annual_fee"]
        net_benefit = yearly - annual_fee

        details = []
        for cb in card.get("category_breakdown", []):
            details.append(f"  - {cb['category']}: {cb['monthly_discount_krw']:,}원")

        section = f"[{rank_label}] {card['card_name']} ({card['card_company']})\n"
        section += f"연회비: {annual_fee:,}원 | 월 예상 할인: {monthly:,}원 | 연 순이익 추정: {net_benefit:,}원\n"
        if card.get("_llm_reason"):
            section += f"  [LLM 선정 이유] {card['_llm_reason']}\n"
        if details:
            section += "\n".join(details) + "\n"

        # 실행 전략 표시
        strategies = card.get("executed_strategies", {})
        if strategies.get("pipeline"):
            section += f"  [실행 전략] pipeline: {', '.join(strategies['pipeline'])}\n"

        warnings = card.get("calc_warnings", [])
        if warnings:
            section += f"  [주의] {'; '.join(warnings)}\n"

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
            "category_breakdown": r.get("category_breakdown", []),
            "executed_strategies": r.get("executed_strategies", {}),
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


@observe(name="exp_d_answer_qa")
def answer_qa_node(state: AgentState):
    """후속 질문 답변."""
    print("[EXP-D] answer_qa_node")
    raw_data = state.get("last_raw_data", "이전 검색 결과 원본이 존재하지 않습니다.")
    qa_prompt = QA_PROMPT.format(raw_data=raw_data)
    response = llm.invoke([SystemMessage(content=qa_prompt)] + state["messages"])
    return {"messages": [AIMessage(content=response.content)]}


# ===========================< Edge Logic >============================

def check_filter_result(state: AgentState) -> Literal["plan", "no_results"]:
    filtered = state.get("shortlist_cards", [])
    return "plan" if filtered else "no_results"


# ===========================< Graph Construction >============================

workflow = StateGraph(AgentState)

workflow.add_node("llm_filter", llm_filter_node)
workflow.add_node("llm_plan", llm_plan_node)
workflow.add_node("strategy_engine", strategy_engine_node)
workflow.add_node("rank_and_explain", rank_and_explain_node)
workflow.add_node("answer_qa", answer_qa_node)

# 메인 흐름: LLM 필터 → LLM 계획 → 전략 엔진 → 설명 → END
workflow.add_edge(START, "llm_filter")
workflow.add_conditional_edges(
    "llm_filter",
    check_filter_result,
    {
        "plan": "llm_plan",
        "no_results": END,
    },
)
workflow.add_edge("llm_plan", "strategy_engine")
workflow.add_edge("strategy_engine", "rank_and_explain")
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
        print(f"\n{'=' * 20} [실험D 테스트: {case['name']}] {'=' * 20}")
        print(f"  총 월소비: {case['total_budget']:,}원")
        for cat, amt in case["category_spending"].items():
            print(f"  - {cat}: {amt:,}원")
        print()

        _init_test_log(case["total_budget"], case["category_spending"])
        start_time = time.time()

        session_id = f"exp_d_{uuid.uuid4().hex[:6]}"
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
                if "llm_plans" in value:
                    print(f"  [LLM 계획] {len(value['llm_plans'])}개 카드 계획 생성")

        elapsed = time.time() - start_time
        _test_log["elapsed_seconds"] = round(elapsed, 2)
        print(f"\n[TIME] 총 소요 시간: {elapsed:.1f}초")

        _save_test_log(case["name"])
        print(f"{'=' * 60}\n")

    # 인터랙티브 메뉴
    while True:
        print("\n[실험D: LLM계획 + 전략엔진] 테스트 케이스를 선택하세요:")
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
