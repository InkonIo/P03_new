# python, calibrates synthetic sales_history baseline using ONE real day of iiko sales data
"""
Real data in hand (from im restaurant director, Dostyk Plaza, 15.10.2026, iiko export):
  data/real_hourly_revenue_20261015.csv    -- hour, guests, revenue, avg_check
  data/real_hourly_item_sales_20261015.csv -- hour, dish (iiko name incl. Combo size suffix), qty

This is ONE real day -- not enough to fit a real elasticity model (need price variation
over time for that, still don't have it), but enough to:
  1. replace the arbitrary per-category BASE_DEMAND constants in data_real_im.py with
     REAL observed category-level daily volume (scaled from combo-variant iiko names to
     plain menu.csv SKUs via substitute_group/category matching)
  2. anchor the weekday multiplier's "today" baseline to something real instead of 100%
     invented, and validate total predicted daily revenue against the real 1,738,320 KZT

Still synthetic: the other 74 days (no historical export yet), and the day-to-day noise.
This narrows the gap, it does not close it -- documented honestly in the report.
"""
import pandas as pd
from pathlib import Path
import re

DATA_DIR = Path(__file__).parent / "data"

# iiko combo-size variants ("Бол.", "Стд.", "XL") all map to one menu.csv SKU (the base item);
# iiko CSO (custom size options) for Наггетсы/Креветки collapse to the single matching SKU too.
SIZE_SUFFIX_RE = re.compile(r"\s+(Бол\.|Стд\.|XL|CSO)\s*\d*\s*(шт)?\s*$", re.IGNORECASE)
COMBO_PREFIX_RE = re.compile(r"^Combo\s+", re.IGNORECASE)

# manual overrides where iiko naming doesn't reduce cleanly via regex
NAME_OVERRIDES = {
    "наггетсы 10 шт": "наггетсы",
    "наггетсы 6 шт": "наггетсы",
    "наггетсы 4 шт": "наггетсы",
    "наггетсы 20 шт": "наггетсы",
    "креветки 4 шт": "креветки",
    "креветки 6 шт": "креветки",
    "креветки 10 шт": "креветки",
    "чизбургер i'm mini": "i'm mini",
    "чикенбургер i'm mini": "i'm mini",
    "гамбургер i'm mini": "i'm mini",
    "наггетсы 4 i'm mini": "i'm mini",
    "салат цезарь с курицей": "салат цезарь с курицей",
    "салат цезарь с креветками": "салат цезарь с креветками",
    "цезарь ролл": "цезарь ролл",
    "цезар ролл": "цезарь ролл",
    "пирожок вишневый": "вишнёвый пирожок",
    "пирожок лесная ягода-сыр": "пирожок «лесная ягода – сливочный сыр»",
    "биг чикен де люкс": "биг чикен делюкс",
    "дабл биг бургер": "double big burger",
    "биг биф де люкс": "биф биг делюкс",
    "чикен тейсти дж.": "чикен тейсти джуниор",
    "наггетсы 10": "наггетсы",
    "наггетсы 10 стд": "наггетсы",
}


def normalize_dish_name(raw: str) -> str:
    s = raw.strip()
    s = COMBO_PREFIX_RE.sub("", s)
    s = SIZE_SUFFIX_RE.sub("", s)
    s = s.strip().lower()
    return NAME_OVERRIDES.get(s, s)


def load_real_sales():
    sales = pd.read_csv(DATA_DIR / "real_hourly_item_sales_20261015.csv")
    sales["is_combo"] = sales["dish"].str.startswith("Combo")
    sales["normalized"] = sales["dish"].apply(normalize_dish_name)
    return sales


def match_to_menu(sales: pd.DataFrame, menu: pd.DataFrame) -> pd.DataFrame:
    menu_lookup = {row["name"].strip().lower(): row["sku_id"] for _, row in menu.iterrows()}
    menu_cat = {row["sku_id"]: row["category"] for _, row in menu.iterrows()}

    def match(normalized):
        if normalized in menu_lookup:
            return menu_lookup[normalized]
        return None

    sales = sales.copy()
    sales["matched_sku"] = sales["normalized"].apply(match)
    sales["matched_category"] = sales["matched_sku"].map(menu_cat)
    return sales


def calibrate_category_demand(matched_sales: pd.DataFrame) -> dict:
    """Category-level real daily unit volume: a combo sale counts as 1 'core item' unit
    for the category of its underlying burger/chicken item (combos live in their own
    Combo category on the website, but a combo order IS a burger-category order in terms
    of real guest demand for that dish)."""
    direct = matched_sales[matched_sales.matched_category.notna()]
    by_cat = direct.groupby("matched_category")["qty"].sum().to_dict()
    return by_cat


def calibrate_sku_shares(matched_sales: pd.DataFrame) -> dict:
    """Per-SKU real daily unit volume (collapsing combo-size variants onto their base
    SKU). Used to replace uniform within-category demand split with real observed mix."""
    direct = matched_sales[matched_sales.matched_sku.notna()]
    by_sku = direct.groupby("matched_sku")["qty"].sum().to_dict()
    return by_sku


def export_calibration(menu: pd.DataFrame, matched_sales: pd.DataFrame, out_path: Path):
    """Writes data/category_calibration.csv and data/sku_calibration.csv for data_real_im.py
    to consume when generating the 75-day synthetic sales_history."""
    cat_demand = calibrate_category_demand(matched_sales)
    sku_demand = calibrate_sku_shares(matched_sales)

    cat_df = pd.DataFrame([{"category": k, "real_qty_20261015": v} for k, v in cat_demand.items()])
    cat_df.to_csv(out_path / "category_calibration.csv", index=False)

    sku_df = pd.DataFrame([{"sku_id": k, "real_qty_20261015": v} for k, v in sku_demand.items()])
    sku_df.to_csv(out_path / "sku_calibration.csv", index=False)
    return cat_df, sku_df


if __name__ == "__main__":
    menu = pd.read_csv(DATA_DIR / "menu.csv")
    sales = load_real_sales()
    matched = match_to_menu(sales, menu)

    total = len(matched)
    matched_n = matched["matched_sku"].notna().sum()
    print(f"matched {matched_n}/{total} line items to menu.csv SKUs ({matched_n/total*100:.0f}%)")

    unmatched = matched[matched.matched_sku.isna()][["dish", "normalized", "qty"]].drop_duplicates()
    print("\nunmatched (will stay purely synthetic for these):")
    print(unmatched.to_string(index=False))

    cat_demand = calibrate_category_demand(matched)
    print("\nreal observed daily qty by category (15.10.2026, one restaurant, one day):")
    for cat, qty in sorted(cat_demand.items(), key=lambda x: -x[1]):
        print(f"  {cat}: {qty}")

    real_revenue = pd.read_csv(DATA_DIR / "real_hourly_revenue_20261015.csv")["revenue"].sum()
    print(f"\nreal total revenue that day (all items incl. non-menu extras): {real_revenue:,.0f} tg")

    cat_df, sku_df = export_calibration(menu, matched, DATA_DIR)
    print(f"\nwrote data/category_calibration.csv ({len(cat_df)} categories)")
    print(f"wrote data/sku_calibration.csv ({len(sku_df)} SKUs with real observed volume)")
