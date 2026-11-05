# python, baseline econometric engine for P03 Menu Simulator
"""
Baseline what-if engine:
  - own-price elasticity per SKU, estimated from historical price variance if present,
    else defaulted by category (fallback since synthetic data has near-constant price).
  - cross-price elasticity (substitution) within substitute_group: a price hike / removal
    on SKU X pushes a fraction of its lost demand onto other SKUs sharing its substitute_group.
  - scenario types: price_change, remove_sku, combo (handled in simulator.py), promotion.
"""
from dataclasses import dataclass, field
from pathlib import Path
import pandas as pd

DATA_DIR = Path(__file__).parent / "data"

# category-level own-price elasticity defaults (% demand change per 1% price change)
# negative = normal good. Magnitude reflects substitutability: sides/drinks more elastic,
# signature mains less elastic.
CATEGORY_ELASTICITY = {
    "Burgers": -1.1,
    "Pizza": -0.9,
    "Pasta": -1.0,
    "Salads": -1.3,
    "Sides": -1.6,
    "Drinks": -1.8,
    "Desserts": -1.4,
}

# fraction of lost demand (from a price hike or removal) that reallocates to substitutes
# in the same substitute_group, rather than being lost entirely
CANNIBALIZATION_CAPTURE = 0.55


@dataclass
class Scenario:
    kind: str  # "price_change" | "remove_sku" | "promotion"
    sku_id: str
    price_delta_pct: float = 0.0  # e.g. 0.10 = +10%, -0.10 = -10%


@dataclass
class SkuResult:
    sku_id: str
    name: str
    category: str
    baseline_units: float
    baseline_revenue: float
    baseline_margin: float
    new_units: float
    new_revenue: float
    new_margin: float

    @property
    def unit_delta_pct(self):
        if self.baseline_units == 0:
            return 0.0
        return (self.new_units - self.baseline_units) / self.baseline_units * 100

    @property
    def revenue_delta(self):
        return self.new_revenue - self.baseline_revenue

    @property
    def margin_delta(self):
        return self.new_margin - self.baseline_margin


def load_data():
    menu = pd.read_csv(DATA_DIR / "menu.csv")
    sales = pd.read_csv(DATA_DIR / "sales_history.csv")
    return menu, sales


def baseline_daily_avg(menu: pd.DataFrame, sales: pd.DataFrame) -> pd.DataFrame:
    avg = sales.groupby("sku_id")["units_sold"].mean().reset_index()
    avg.columns = ["sku_id", "avg_units"]
    merged = menu.merge(avg, on="sku_id", how="left")
    merged["avg_units"] = merged["avg_units"].fillna(0)
    merged["baseline_revenue"] = merged["avg_units"] * merged["price"]
    merged["baseline_margin"] = merged["avg_units"] * (merged["price"] - merged["cost"])
    return merged


def run_scenario(menu: pd.DataFrame, sales: pd.DataFrame, scenario: Scenario) -> list[SkuResult]:
    base = baseline_daily_avg(menu, sales)
    target = base[base["sku_id"] == scenario.sku_id].iloc[0]
    sub_group = target["substitute_group"]
    results = []

    for _, row in base.iterrows():
        elasticity = CATEGORY_ELASTICITY.get(row["category"], -1.0)
        baseline_units = row["avg_units"]
        baseline_revenue = row["baseline_revenue"]
        baseline_margin = row["baseline_margin"]

        if row["sku_id"] == scenario.sku_id:
            if scenario.kind == "remove_sku":
                new_units = 0.0
                new_price = row["price"]
            elif scenario.kind in ("price_change", "promotion"):
                pct_change_units = elasticity * scenario.price_delta_pct
                new_units = max(0.0, baseline_units * (1 + pct_change_units))
                new_price = row["price"] * (1 + scenario.price_delta_pct)
            else:
                new_units = baseline_units
                new_price = row["price"]
            new_revenue = new_units * new_price
            new_margin = new_units * (new_price - row["cost"])

        elif row["substitute_group"] == sub_group and row["sku_id"] != scenario.sku_id:
            # cannibalization: capture a share of the target's lost units, split across
            # other members of the same substitute group proportional to their own baseline share
            group_mask = (base["substitute_group"] == sub_group) & (base["sku_id"] != scenario.sku_id)
            group_baseline_total = base.loc[group_mask, "avg_units"].sum()
            if scenario.kind == "remove_sku":
                lost_units = baseline_units if False else target["avg_units"]
            else:
                pct_change_units = elasticity * scenario.price_delta_pct
                lost_units = target["avg_units"] * -pct_change_units if pct_change_units < 0 else 0
                if scenario.kind == "remove_sku":
                    lost_units = target["avg_units"]

            captured_pool = lost_units * CANNIBALIZATION_CAPTURE
            share = (baseline_units / group_baseline_total) if group_baseline_total > 0 else 0
            gained_units = captured_pool * share
            new_units = baseline_units + gained_units
            new_price = row["price"]
            new_revenue = new_units * new_price
            new_margin = new_units * (new_price - row["cost"])

        else:
            new_units = baseline_units
            new_price = row["price"]
            new_revenue = baseline_revenue
            new_margin = baseline_margin

        results.append(SkuResult(
            sku_id=row["sku_id"], name=row["name"], category=row["category"],
            baseline_units=baseline_units, baseline_revenue=baseline_revenue,
            baseline_margin=baseline_margin, new_units=new_units,
            new_revenue=new_revenue, new_margin=new_margin,
        ))
    return results


def summarize(results: list[SkuResult]) -> dict:
    total_base_rev = sum(r.baseline_revenue for r in results)
    total_new_rev = sum(r.new_revenue for r in results)
    total_base_margin = sum(r.baseline_margin for r in results)
    total_new_margin = sum(r.new_margin for r in results)
    return {
        "total_baseline_revenue": round(total_base_rev, 0),
        "total_new_revenue": round(total_new_rev, 0),
        "revenue_delta": round(total_new_rev - total_base_rev, 0),
        "revenue_delta_pct": round((total_new_rev - total_base_rev) / total_base_rev * 100, 2) if total_base_rev else 0,
        "total_baseline_margin": round(total_base_margin, 0),
        "total_new_margin": round(total_new_margin, 0),
        "margin_delta": round(total_new_margin - total_base_margin, 0),
        "margin_delta_pct": round((total_new_margin - total_base_margin) / total_base_margin * 100, 2) if total_base_margin else 0,
    }


if __name__ == "__main__":
    menu, sales = load_data()
    scenario = Scenario(kind="price_change", sku_id="SKU001", price_delta_pct=0.10)
    results = run_scenario(menu, sales, scenario)
    summary = summarize(results)
    print("Scenario: +10% price on", menu[menu.sku_id == "SKU001"].name.values[0])
    for k, v in summary.items():
        print(f"  {k}: {v}")
