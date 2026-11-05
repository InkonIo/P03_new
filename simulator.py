# python, orchestrates baseline + persona layers, combo scenarios, and LLM tool-calling entrypoint
from dataclasses import asdict
from pathlib import Path
import json
import pandas as pd

from elasticity import load_data, run_scenario, summarize, Scenario, baseline_daily_avg
from personas import simulate_personas, reactions_summary, simulate_promo_personas, promo_reactions_summary
import promo_engine

DATA_DIR = Path(__file__).parent / "data"


def simulate_price_change(sku_id: str, price_delta_pct: float) -> dict:
    menu, sales = load_data()
    target_row = menu[menu.sku_id == sku_id]
    if target_row.empty:
        return {"error": f"unknown sku_id {sku_id}"}
    target = target_row.iloc[0]

    scenario = Scenario(kind="price_change", sku_id=sku_id, price_delta_pct=price_delta_pct)
    results = run_scenario(menu, sales, scenario)
    econ_summary = summarize(results)

    personas = simulate_personas(category=target["category"], price_delta_pct=price_delta_pct)
    persona_summary = reactions_summary(personas)

    return {
        "scenario": {"type": "price_change", "sku_id": sku_id, "sku_name": target["name"], "price_delta_pct": price_delta_pct},
        "econometric": econ_summary,
        "per_sku_top_movers": _top_movers(results),
        "persona_simulation": persona_summary,
    }


def simulate_removal(sku_id: str) -> dict:
    menu, sales = load_data()
    target_row = menu[menu.sku_id == sku_id]
    if target_row.empty:
        return {"error": f"unknown sku_id {sku_id}"}
    target = target_row.iloc[0]

    scenario = Scenario(kind="remove_sku", sku_id=sku_id)
    results = run_scenario(menu, sales, scenario)
    econ_summary = summarize(results)

    personas = simulate_personas(category=target["category"], removed=True)
    persona_summary = reactions_summary(personas)

    return {
        "scenario": {"type": "remove_sku", "sku_id": sku_id, "sku_name": target["name"]},
        "econometric": econ_summary,
        "per_sku_top_movers": _top_movers(results),
        "persona_simulation": persona_summary,
    }


def simulate_combo(combo_id: str) -> dict:
    menu, sales = load_data()
    combos = pd.read_csv(DATA_DIR / "combos.csv")
    combo_row = combos[combos.combo_id == combo_id]
    if combo_row.empty:
        return {"error": f"unknown combo_id {combo_id}"}
    combo = combo_row.iloc[0]
    sku_ids = combo["sku_ids"].split("|")

    base = baseline_daily_avg(menu, sales)
    included = base[base.sku_id.isin(sku_ids)]
    baseline_units_sum = included["avg_units"].sum()
    baseline_revenue_sum = included["baseline_revenue"].sum()
    baseline_margin_sum = included["baseline_margin"].sum()

    # assume combo attach rate: 20% of baseline joint demand converts to combo purchase,
    # at combo price, with a modest +12% uplift in total units sold together (bundling effect)
    attach_rate = 0.20
    uplift = 1.12
    combo_units = baseline_units_sum / len(sku_ids) * attach_rate * uplift
    combo_cost = included["cost"].sum()
    combo_revenue = combo_units * combo["combo_price"]
    combo_margin = combo_units * (combo["combo_price"] - combo_cost)

    remaining_units_sum = baseline_units_sum * (1 - attach_rate)
    remaining_revenue = remaining_units_sum / baseline_units_sum * baseline_revenue_sum if baseline_units_sum else 0
    remaining_margin = remaining_units_sum / baseline_units_sum * baseline_margin_sum if baseline_units_sum else 0

    new_total_revenue = remaining_revenue + combo_revenue
    new_total_margin = remaining_margin + combo_margin

    personas = simulate_personas(category="Combo", price_delta_pct=-combo["discount_pct"])
    persona_summary = reactions_summary(personas)

    return {
        "scenario": {"type": "combo", "combo_id": combo_id, "combo_name": combo["name"], "items": sku_ids, "combo_price": int(combo["combo_price"])},
        "econometric": {
            "baseline_revenue_items_separately": round(baseline_revenue_sum, 0),
            "baseline_margin_items_separately": round(baseline_margin_sum, 0),
            "projected_revenue_with_combo": round(new_total_revenue, 0),
            "projected_margin_with_combo": round(new_total_margin, 0),
            "revenue_delta": round(new_total_revenue - baseline_revenue_sum, 0),
            "margin_delta": round(new_total_margin - baseline_margin_sum, 0),
            "assumed_attach_rate": attach_rate,
            "assumed_bundling_uplift": uplift,
        },
        "persona_simulation": persona_summary,
    }


def simulate_promo(channel: str, guest_discount_pct: float, funded_by: str = "", duration_days: int = 14) -> dict:
    """Новая акция: ориентир по аналогам из реальной истории (promo_engine) + реакция 15 AI-персон."""
    out = promo_engine.forecast_promo(channel, guest_discount_pct, funded_by, duration_days)
    if "error" in out:
        return out
    sc = out["scenario"]
    out["persona_simulation"] = promo_reactions_summary(simulate_promo_personas(sc["channel"], sc["guest_discount_pct"]))
    return out


def promo_history(promo: str) -> dict:
    """Факт по прошлой акции: что было с гостями, чеком и выручкой после старта + окупаемость по прогнозу маркетинга."""
    return promo_engine.promo_history(promo)


def _top_movers(results, n=5):
    sorted_results = sorted(results, key=lambda r: abs(r.revenue_delta), reverse=True)[:n]
    return [
        {
            "sku_id": r.sku_id, "name": r.name,
            "unit_delta_pct": round(r.unit_delta_pct, 1),
            "revenue_delta": round(r.revenue_delta, 0),
            "margin_delta": round(r.margin_delta, 0),
        }
        for r in sorted_results
    ]


# --- agentic tool-calling entrypoint -------------------------------------------------
TOOLS = [
    {
        "name": "simulate_price_change",
        "description": "Simulate changing the price of one SKU by a percentage (e.g. +10% = 0.10, -10% = -0.10). Returns econometric revenue/margin impact plus AI persona reactions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "sku_id": {"type": "string", "description": "e.g. SKU001"},
                "price_delta_pct": {"type": "number", "description": "0.10 for +10%, -0.15 for -15%"},
            },
            "required": ["sku_id", "price_delta_pct"],
        },
    },
    {
        "name": "simulate_removal",
        "description": "Simulate removing a SKU from the menu entirely. Returns cannibalization to substitute items and persona reactions.",
        "input_schema": {
            "type": "object",
            "properties": {"sku_id": {"type": "string"}},
            "required": ["sku_id"],
        },
    },
    {
        "name": "simulate_combo",
        "description": "Simulate launching a combo/bundle deal. Returns projected revenue/margin vs items sold separately.",
        "input_schema": {
            "type": "object",
            "properties": {"combo_id": {"type": "string", "description": "e.g. COMBO01"}},
            "required": ["combo_id"],
        },
    },
]

PROMO_IDS = "; ".join(f"{e['id']} = {e['name']}" for e in promo_engine.EVENTS)
TOOLS += [
    {
        "name": "promo_history",
        "description": "How a PAST promotion actually performed in the real data of one restaurant (Dostyk Plaza, Jun-Aug 2026): "
                       "guests per day, average check and revenue before/after the start, versus normal fluctuation. "
                       f"Known promos: {PROMO_IDS}.",
        "input_schema": {"type": "object", "properties": {"promo": {"type": "string", "description": "promo id, e.g. yandex_aug04"}},
                         "required": ["promo"]},
    },
    {
        "name": "simulate_promo",
        "description": "Estimate the effect of a NEW promotion by analogs from past promos (same channel, similar discount). "
                       "Returns expected change of guests/average check/revenue per day with a range, break-even uplift for "
                       "restaurant-funded discounts, and reactions of 15 AI personas. This is an orientation, not a forecast.",
        "input_schema": {"type": "object", "properties": {
            "channel": {"type": "string", "enum": promo_engine.CHANNELS},
            "guest_discount_pct": {"type": "number", "description": "discount the guest sees, in percent, e.g. 30"},
            "funded_by": {"type": "string", "enum": promo_engine.FUNDING,
                          "description": "who pays: ресторан, пополам (typical Yandex/Wolt), агрегатор (typical Glovo). Omit for the channel default"},
            "duration_days": {"type": "integer", "description": "promo length in days, default 14"}},
            "required": ["channel", "guest_discount_pct"]},
    },
]

TOOL_IMPL = {
    "promo_history": lambda args: promo_history(args["promo"]),
    "simulate_promo": lambda args: simulate_promo(args["channel"], args["guest_discount_pct"],
                                                   args.get("funded_by", ""), args.get("duration_days", 14)),
    "simulate_price_change": lambda args: simulate_price_change(args["sku_id"], args["price_delta_pct"]),
    "simulate_removal": lambda args: simulate_removal(args["sku_id"]),
    "simulate_combo": lambda args: simulate_combo(args["combo_id"]),
}


def ask_agent(question: str) -> str:
    """Natural-language entrypoint (CLI). The agent loop with a step trace lives in agent_trace.run_agent;
    the website shows that trace. Without ANTHROPIC_API_KEY it runs the transparent rule-based planner."""
    from agent_trace import run_agent
    return run_agent(question, use_thinking=False).answer


if __name__ == "__main__":
    print(json.dumps(simulate_price_change("SKU001", 0.10), indent=2, ensure_ascii=False))
    print()
    print(json.dumps(simulate_removal("SKU006"), indent=2, ensure_ascii=False))
    print()
    print(json.dumps(simulate_combo("COMBO01"), indent=2, ensure_ascii=False))