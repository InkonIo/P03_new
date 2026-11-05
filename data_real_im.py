# python, real menu scrape -> csv for P03 Menu Simulator (I'M Kazakhstan, im.kz/products)
"""
Real menu/prices scraped from https://im.kz/products on 2026-11-03 (public menu page,
no login, no personal/guest data -- just products & prices, which the project brief allows
as "предоставленные с разрешением данные"/own research; verify with KOZ AI if this needs
formal sign-off before using in the final submission).

im.kz does NOT publish cost/margin or historical per-day sales anywhere public, so:
  - cost = estimated at 35% of price (typical fast-food food cost %, documented assumption)
  - sales_history = still SYNTHETIC (same generator logic as before), just layered on top
    of the REAL menu/prices instead of invented ones.

This keeps the deliverable honest: real prices, clearly-labeled assumption for cost,
clearly-labeled synthetic sales volumes (im.kz doesn't expose real sales data publicly).
"""
import csv
import random
from pathlib import Path

random.seed(42)
DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

COST_RATIO = 0.35  # documented assumption: no public cost data from im.kz

# (name, category, price, substitute_group)
REAL_MENU = [
    # Бургеры
    ("Биф Тейсти", "Бургеры", 3100, "burger_beef_premium"),
    ("Дабл Гранд Чизбургер", "Бургеры", 2850, "burger_beef_premium"),
    ("Big Burger", "Бургеры", 2200, "burger_beef_core"),
    ("Гранд Чизбургер", "Бургеры", 1950, "burger_beef_core"),
    ("Цезарь Ролл", "Бургеры", 1850, "burger_chicken"),
    ("Чикен Классик", "Бургеры", 1700, "burger_chicken"),
    ("Дабл Чизбургер", "Бургеры", 1550, "burger_beef_core"),
    ("Чикен Тейсти Джуниор", "Бургеры", 2400, "burger_chicken"),
    ("Чизбургер", "Бургеры", 950, "burger_beef_core"),
    ("Гамбургер", "Бургеры", 900, "burger_beef_core"),
    ("Чикенбургер", "Бургеры", 900, "burger_chicken"),
    ("Биг Чикен Делюкс", "Бургеры", 2600, "burger_chicken"),
    ("Double Big Burger", "Бургеры", 3000, "burger_beef_premium"),
    ("Биф Биг Делюкс", "Бургеры", 3100, "burger_beef_premium"),
    ("Бифкұрт", "Бургеры", 2200, "burger_beef_core"),
    ("Чикенқұрт", "Бургеры", 1800, "burger_chicken"),
    # Combo
    ("Combo стрипсы 10 шт.", "Combo", 4050, "combo_chicken"),
    ("Combo стрипсы 6 шт.", "Combo", 3250, "combo_chicken"),
    ("Combo Биф Тейсти", "Combo", 4150, "combo_beef"),
    ("Combo Double Big Burger", "Combo", 4050, "combo_beef"),
    ("Combo Дабл Гранд Чизбургер", "Combo", 3950, "combo_beef"),
    ("Combo Чикен Тейсти", "Combo", 3700, "combo_chicken"),
    ("Combo Big Burger", "Combo", 3250, "combo_beef"),
    ("Combo Гранд Чизбургер", "Combo", 3050, "combo_beef"),
    ("Combo Цезарь Ролл", "Combo", 2850, "combo_chicken"),
    ("Combo Наггетс 10 шт.", "Combo", 2750, "combo_chicken"),
    ("Combo Чикен Классик", "Combo", 2650, "combo_chicken"),
    ("Combo Дабл Чизбургер", "Combo", 2700, "combo_beef"),
    ("Combo Чикен Тейсти Джуниор", "Combo", 3300, "combo_chicken"),
    ("Combo Наггетс 6 шт.", "Combo", 2350, "combo_chicken"),
    ("Combo Френч Дог с курицей", "Combo", 3250, "combo_chicken"),
    ("Combo Биг Чикен Делюкс", "Combo", 3700, "combo_chicken"),
    ("Combo Биг Делюкс", "Combo", 4150, "combo_beef"),
    # Закуски
    ("Стрипсы", "Закуски", 1400, "snack_chicken"),
    ("Куриные крылья", "Закуски", 1800, "snack_chicken"),
    ("Крылья (8 штук)", "Закуски", 3550, "snack_chicken"),
    ("Креветки", "Закуски", 1900, "snack_seafood"),
    ("Наггетсы", "Закуски", 800, "snack_chicken"),
    ("Картофель по-деревенски", "Закуски", 950, "snack_potato"),
    ("Картофель Фри", "Закуски", 650, "snack_potato"),
    ("Морковные палочки", "Закуски", 550, "snack_veg"),
    ("Яблочные дольки", "Закуски", 550, "snack_veg"),
    ("Баскет 6 крыльев, 10 наггетсов", "Закуски", 4100, "snack_chicken"),
    # Соусы
    ("Кетчуп", "Соусы", 200, "sauce"),
    ("Соус 1000 островов", "Соусы", 200, "sauce"),
    ("Соус Барбекю", "Соусы", 200, "sauce"),
    ("Соус Горчичный", "Соусы", 200, "sauce"),
    ("Сырный соус", "Соусы", 200, "sauce"),
    ("Соус Чесночный", "Соусы", 200, "sauce"),
    # Холодные напитки
    ("Молочный коктейль ванильный", "Холодные напитки", 1050, "drink_shake"),
    ("Молочный коктейль Белый персик", "Холодные напитки", 1050, "drink_shake"),
    ("Молочный коктейль шоколадный", "Холодные напитки", 1050, "drink_shake"),
    ("Молочный коктейль клубничный", "Холодные напитки", 1050, "drink_shake"),
    ("Fuse Tea Манго-Ананас", "Холодные напитки", 600, "drink_tea"),
    ("Fuse Tea Манго-Ромашка", "Холодные напитки", 600, "drink_tea"),
    ("Нектар Piko Mini яблочный", "Холодные напитки", 500, "drink_juice"),
    ("Нектар Piko Mini персиковый", "Холодные напитки", 500, "drink_juice"),
    ("Нектар Piko Mini мультифруктовый", "Холодные напитки", 500, "drink_juice"),
    ("Нектар Piko Mini апельсиновый", "Холодные напитки", 500, "drink_juice"),
    ("BonAqua негазированная", "Холодные напитки", 450, "drink_water"),
    ("BonAqua газированная", "Холодные напитки", 450, "drink_water"),
    ("Sprite", "Холодные напитки", 450, "drink_soda"),
    ("Fanta", "Холодные напитки", 450, "drink_soda"),
    ("Coca-Cola без сахара", "Холодные напитки", 450, "drink_soda"),
    ("Coca-Cola", "Холодные напитки", 450, "drink_soda"),
    ("Fuse Tea Персик", "Холодные напитки", 450, "drink_tea"),
    ("Клубничный айс кофе", "Холодные напитки", 1200, "drink_coffee"),
    ("Айс Кофе", "Холодные напитки", 1200, "drink_coffee"),
    # I'M Café
    ("Капучино карамельное яблоко", "I'M Café", 1100, "cafe_coffee"),
    ("Панини с тунцом", "I'M Café", 2000, "cafe_food"),
    ("Панини с курицей", "I'M Café", 1900, "cafe_food"),
    ("Какао", "I'M Café", 1400, "cafe_coffee"),
    ("Латте", "I'M Café", 1300, "cafe_coffee"),
    ("Капучино", "I'M Café", 1250, "cafe_coffee"),
    ("Кофе с молоком", "I'M Café", 900, "cafe_coffee"),
    ("Американо", "I'M Café", 950, "cafe_coffee"),
    ("Чай кенийский", "I'M Café", 700, "cafe_tea"),
    ("Эспрессо", "I'M Café", 600, "cafe_coffee"),
    ("Френч дог с говяжим мясом", "I'M Café", 2150, "cafe_food"),
    # Десерты
    ("Синнабон", "Десерты", 1300, "dessert_pastry"),
    ("Айс Микс Ананас", "Десерты", 1100, "dessert_icecream"),
    ("Мороженое с ананасовым наполнителем", "Десерты", 850, "dessert_icecream"),
    ("Айс Микс Шоколад", "Десерты", 1100, "dessert_icecream"),
    ("Айс Микс Карамель", "Десерты", 1100, "dessert_icecream"),
    ("Айс Микс Клубника", "Десерты", 1100, "dessert_icecream"),
    ("Мороженое с карамельным наполнителем", "Десерты", 850, "dessert_icecream"),
    ("Мороженое с шоколадным наполнителем", "Десерты", 850, "dessert_icecream"),
    ("Мороженое с клубничным наполнителем", "Десерты", 850, "dessert_icecream"),
    ("Вишнёвый пирожок", "Десерты", 600, "dessert_pastry"),
    ("Рожок", "Десерты", 500, "dessert_icecream"),
    ("Трайфл Тирамису", "Десерты", 1850, "dessert_trifle"),
    ("Трайфл Медовый", "Десерты", 1550, "dessert_trifle"),
    ("Трайфл Лесные ягоды", "Десерты", 1800, "dessert_trifle"),
    ("Айс Микс Тройная Шоколадная Крошка", "Десерты", 1100, "dessert_icecream"),
    ("Пирожок «Лесная ягода – Сливочный сыр»", "Десерты", 700, "dessert_pastry"),
    # Салаты
    ("Коул Слоу", "Салаты", 1100, "salad"),
    ("Салат Цезарь с креветками", "Салаты", 1900, "salad"),
    ("Салат Цезарь с курицей", "Салаты", 1450, "salad"),
    # Завтраки
    ("Бифкұрт маффин", "Завтраки", 2050, "breakfast_beef"),
    ("Чикенқұрт маффин", "Завтраки", 1750, "breakfast_chicken"),
    ("Чикен Фреш Ролл", "Завтраки", 1850, "breakfast_chicken"),
    ("Фреш Ролл", "Завтраки", 1700, "breakfast_chicken"),
    ("Биф Маффин с Яйцом", "Завтраки", 1450, "breakfast_beef"),
    ("Чикен Фреш Маффин", "Завтраки", 1250, "breakfast_chicken"),
    ("Маффин с Яйцом и Ветчиной", "Завтраки", 1250, "breakfast_egg"),
    ("Биф Маффин", "Завтраки", 1100, "breakfast_beef"),
    ("Маффин с Яйцом и Сыром", "Завтраки", 1050, "breakfast_egg"),
    ("Тост с Сыром и Ветчиной", "Завтраки", 850, "breakfast_toast"),
    ("Тост с Сыром", "Завтраки", 650, "breakfast_toast"),
    ("Beef box", "Завтраки", 2600, "breakfast_beef"),
    ("Muffin box", "Завтраки", 2250, "breakfast_egg"),
    ("Toast Box", "Завтраки", 1400, "breakfast_toast"),
    ("Маффин с Омлетом и Сыром", "Завтраки", 1200, "breakfast_egg"),
    ("Маффин с омлетом и ветчиной", "Завтраки", 1400, "breakfast_egg"),
    ("Биф Маффин с омлетом", "Завтраки", 1600, "breakfast_beef"),
    ("Хашбраун", "Завтраки", 450, "breakfast_toast"),
    # I'M Mini
    ("I'M Mini", "I'M Mini", 3150, "mini_box"),
    # Горячие напитки
    ("Согревающий морс клюква-ирга", "Горячие напитки", 800, "hotdrink_other"),
    ("Латте белый персик", "Горячие напитки", 1100, "hotdrink_coffee"),
    ("Латте стандартный", "Горячие напитки", 1050, "hotdrink_coffee"),
    ("Глясе", "Горячие напитки", 800, "hotdrink_coffee"),
    ("Чай зелёный", "Горячие напитки", 400, "hotdrink_tea"),
    ("Чай чёрный", "Горячие напитки", 400, "hotdrink_tea"),
]

# category-level base daily demand. Categories with a real calibration (from one real iiko
# day, 15.10.2026, Dostyk Plaza) use that; everything else falls back to an expert estimate,
# scaled to roughly the same per-restaurant order of magnitude as the calibrated categories.
BASE_DEMAND_FALLBACK = {
    "Бургеры": 55, "Combo": 40, "Закуски": 45, "Соусы": 70,
    "Холодные напитки": 50, "I'M Café": 20, "Десерты": 25,
    "Салаты": 12, "Завтраки": 18, "I'M Mini": 5, "Горячие напитки": 15,
}


def load_calibration():
    """Real daily unit counts from data/category_calibration.csv and sku_calibration.csv,
    produced by data_calibrate.py from the real iiko export the restaurant director sent
    (15.10.2026, Dostyk Plaza, one day). Returns empty dicts if calibration hasn't been run
    yet (data_real_im.py still works standalone with pure fallback estimates)."""
    import pandas as pd
    cat_path = DATA_DIR / "category_calibration.csv"
    sku_path = DATA_DIR / "sku_calibration.csv"
    cat_calib, sku_calib = {}, {}
    if cat_path.exists():
        cat_calib = pd.read_csv(cat_path).set_index("category")["real_qty_20261015"].to_dict()
    if sku_path.exists():
        sku_calib = pd.read_csv(sku_path).set_index("sku_id")["real_qty_20261015"].to_dict()
    return cat_calib, sku_calib

WEEKDAY_MULT = [0.85, 0.85, 0.9, 0.95, 1.2, 1.4, 1.3]  # Mon..Sun


def gen_menu():
    rows = []
    for i, (name, cat, price, sub_group) in enumerate(REAL_MENU, start=1):
        cost = round(price * COST_RATIO / 10) * 10
        rows.append({
            "sku_id": f"SKU{i:03d}",
            "name": name,
            "category": cat,
            "price": price,
            "cost": cost,
            "substitute_group": sub_group,
        })
    with open(DATA_DIR / "menu.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)
    return rows


def gen_combos(menu_rows):
    """im.kz already sells most items as ready-made Combo SKUs (own category), so the
    'combo' scenario in the simulator treats a NEW/unreleased bundle idea -- here we pick
    a few items NOT already in the Combo category to propose as new bundles."""
    by_name = {r["name"]: r for r in menu_rows}
    combo_defs = [
        ("Новое Комбо: Стрипсы + Фри + Кола", ["Стрипсы", "Картофель Фри", "Coca-Cola"], 0.15),
        ("Новое Комбо: Завтрак дуо", ["Тост с Сыром", "Американо"], 0.12),
        ("Новое Комбо: Салат + сок", ["Салат Цезарь с курицей", "Нектар Piko Mini апельсиновый"], 0.10),
        ("Новое Комбо: Сладкая пара", ["Синнабон", "Айс Кофе"], 0.08),
    ]
    rows = []
    for combo_id, (name, items, discount) in enumerate(combo_defs, start=1):
        sku_ids = [by_name[i]["sku_id"] for i in items]
        base_price = sum(int(by_name[i]["price"]) for i in items)
        combo_price = round(base_price * (1 - discount) / 50) * 50
        rows.append({
            "combo_id": f"COMBO{combo_id:02d}",
            "name": name,
            "sku_ids": "|".join(sku_ids),
            "base_price_sum": base_price,
            "combo_price": combo_price,
            "discount_pct": discount,
        })
    with open(DATA_DIR / "combos.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)
    return rows


def gen_sales_history(menu_rows, n_days=75):
    """Sales volumes for 75 days. Where real calibration exists (category_calibration.csv /
    sku_calibration.csv, built from the real iiko export for 15.10.2026), each SKU's base
    daily demand is anchored to its REAL observed quantity that day. Categories/SKUs without
    a real match fall back to the documented expert estimate (BASE_DEMAND_FALLBACK) -- im.kz
    doesn't publish per-SKU daily sales, and we only have one real day from the restaurant,
    not a full historical series, so both remain explicit, labeled assumptions layered on
    top of the one real data point we do have."""
    rows = []
    import datetime
    start = datetime.date(2026, 8, 20)
    by_cat_count = {}
    for r in menu_rows:
        by_cat_count[r["category"]] = by_cat_count.get(r["category"], 0) + 1

    cat_calib, sku_calib = load_calibration()

    for d in range(n_days):
        day = start + datetime.timedelta(days=d)
        wd = day.weekday()
        day_mult = WEEKDAY_MULT[wd]
        for r in menu_rows:
            sku_id = r["sku_id"]
            if sku_id in sku_calib:
                # real observed volume for this exact SKU on 15.10.2026 -> use as the
                # "typical weekday" anchor directly (15.10.2026 was a Thursday)
                base = sku_calib[sku_id] / WEEKDAY_MULT[3]
            elif r["category"] in cat_calib:
                # category has real data but this specific SKU doesn't (e.g. it exists on
                # im.kz but wasn't ordered that one day) -> split the category's real
                # leftover volume evenly among its uncalibrated SKUs
                cat_skus = [m for m in menu_rows if m["category"] == r["category"]]
                calibrated_in_cat = sum(sku_calib.get(m["sku_id"], 0) for m in cat_skus)
                uncalibrated_in_cat = [m for m in cat_skus if m["sku_id"] not in sku_calib]
                leftover = max(0, cat_calib[r["category"]] - calibrated_in_cat)
                base = (leftover / len(uncalibrated_in_cat) if uncalibrated_in_cat else 0) / WEEKDAY_MULT[3]
            else:
                base = BASE_DEMAND_FALLBACK.get(r["category"], 15) / by_cat_count[r["category"]]

            noise = random.uniform(0.75, 1.25)
            trend = 1.0 + 0.001 * d
            units = max(0, round(base * day_mult * noise * trend))
            rows.append({
                "date": day.isoformat(),
                "sku_id": sku_id,
                "units_sold": units,
                "revenue": units * int(r["price"]),
            })
    with open(DATA_DIR / "sales_history.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)
    return rows


if __name__ == "__main__":
    menu = gen_menu()
    combos = gen_combos(menu)
    sales = gen_sales_history(menu)
    print(f"REAL menu (im.kz): {len(menu)} SKUs -> data/menu.csv")
    print(f"NEW proposed combos: {len(combos)} -> data/combos.csv")
    print(f"SYNTHETIC sales_history: {len(sales)} rows ({len(sales)//len(menu)} days) -> data/sales_history.csv")
    print()
    print("NOTE: prices are REAL (scraped im.kz/products, 2026-11-03).")
    print(f"      cost = {int(COST_RATIO*100)}% of price (documented assumption, im.kz doesn't publish cost/margin).")
    print("      sales volumes are SYNTHETIC (im.kz doesn't publish real sales data publicly).")
