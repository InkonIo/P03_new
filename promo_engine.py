# python 3.10+, promo analytics engine for P03: history of promos, analog forecast, price-based break-even (no streamlit here)
"""
Что считает:
  1. effect()          факт: как менялись чеки/средний чек/выручка в первые N дней после старта акции (до/после, по дням недели)
  2. noise_band()      диапазон обычных колебаний без акций (чтобы не принимать шум за эффект)
  3. promo_history()   карточка прошлой акции: факт + вердикт + окупаемость по прогнозу маркетинга
  4. forecast_promo()  ориентир для НОВОЙ акции по аналогам из истории (тот же канал и похожая глубина скидки)
  5. breakeven_table() по ценам из писем агрегаторов: сколько прироста продаж позиции нужно, чтобы скидка ресторана окупилась

Честные границы: данные одного ресторана за 92 дня, только итоги по дням; акции шли внахлёст; себестоимость позиций
берётся как доля от цены (допущение из menu.csv), а не из техкарт. Всё это ориентиры для решения и A/B-теста, не прогноз.
"""
import re
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

DATA = Path(__file__).parent / "data"
DAILY = DATA / "real_daily_revenue.csv"
CAL = DATA / "promo_calendar.xlsx"

# Акции внутри периода дневных продаж (01.06-31.08.2026). start = первый день эффекта.
EVENTS = [
    dict(id="icup", name="I'M CUP: Биг Делюкс + подарки Coca-Cola", start="2026-07-08", channel="Ресторан",
         guest_discount=0, funded_by="ресторан (подарки и запуск новинки)", note="в ресторане, приложение и Drive; подарки до 19.07"),
    dict(id="glovo_jul17", name="Glovo −30%: Combo Биф Тейсти / Цезарь Ролл", start="2026-07-17", channel="Glovo",
         guest_discount=30, funded_by="агрегатор", note="доставка, скидку платит агрегатор"),
    dict(id="yandex_jul21", name="Yandex −40%: Тейсти Джуниор / Наггетсы 10", start="2026-07-21", channel="Yandex",
         guest_discount=40, funded_by="ресторан", note="доставка, цена снижена рестораном (−20% к цене)"),
    dict(id="glovo_jul24", name="Glovo −30%: Бифкурт / Чикенкурт", start="2026-07-24", channel="Glovo",
         guest_discount=30, funded_by="агрегатор", note="доставка, Алматы с 24.07"),
    dict(id="glovo_aug01", name="Glovo −30%: Combo Чикен Классик / Наггетсы 6", start="2026-08-01", channel="Glovo",
         guest_discount=30, funded_by="агрегатор", note="доставка, скидку платит агрегатор"),
    dict(id="yandex_aug04", name="Yandex −40%: Бифкурт / Чикенкурт", start="2026-08-04", channel="Yandex",
         guest_discount=40, funded_by="ресторан", note="доставка, цена снижена рестораном (−20% к цене)"),
]
CHANNELS = ["Yandex", "Glovo", "Wolt", "Ресторан"]
FOOD_COST_FALLBACK = 0.35


_KEYS = {"icup": (["i'm cup", "im cup", "cup", "имкап", "делюкс", "coca", "кока"], None),
         "glovo_jul17": (["биф тейсти", "цезарь"], "glovo"),
         "yandex_jul21": (["джуниор", "наггетс"], "yandex"),
         "glovo_jul24": (["бифкурт", "чикенкурт"], "glovo"),
         "glovo_aug01": (["чикен классик", "наггетс"], "glovo"),
         "yandex_aug04": (["бифкурт", "чикенкурт"], "yandex")}
_CH = {"yandex": ("yandex", "яндекс"), "glovo": ("glovo", "глово")}


def event_by_id(key: str) -> dict | None:
    """Находит акцию по id, названию или свободному тексту вопроса (канал + позиции + скидка + дата)."""
    key = (key or "").strip().lower()
    for e in EVENTS:
        if key == e["id"] or key == e["name"].lower():
            return e
    best, best_score = None, 0
    for e in EVENTS:
        items, ch = _KEYS[e["id"]]
        score = sum(2 for w in items if w in key)
        if ch and any(w in key for w in _CH[ch]):
            score += 3
        elif ch and any(w in key for o, ws in _CH.items() if o != ch for w in ws):
            score -= 3
        if e["guest_discount"] and f"{e['guest_discount']}%" in key.replace(" ", "").replace("−", "").replace("-", ""):
            score += 1
        d = pd.Timestamp(e["start"])
        if f"{d:%d.%m}" in key or f"{d.day}.{d:%m}" in key:
            score += 4
        if score > best_score:
            best, best_score = e, score
    return best if best_score >= 3 else None


@lru_cache(maxsize=1)
def load_daily() -> pd.DataFrame:
    df = pd.read_csv(DAILY, parse_dates=["date"])
    df["avg_check"] = df["net"] / df["checks"]
    df["wd"] = df["date"].dt.dayofweek
    return df.sort_values("date").reset_index(drop=True)


@lru_cache(maxsize=1)
def load_calendar() -> tuple[pd.DataFrame, pd.DataFrame]:
    return (pd.read_excel(CAL, sheet_name="Промо в ресторанах"),
            pd.read_excel(CAL, sheet_name="Доставка (агрегаторы)"))


@lru_cache(maxsize=1)
def food_cost_ratio() -> float:
    try:
        m = pd.read_csv(DATA / "menu.csv")
        return float((m["cost"] / m["price"]).median())
    except Exception:
        return FOOD_COST_FALLBACK


def effect(df: pd.DataFrame, start: str, before: int = 14, after: int = 7) -> dict | None:
    """Δ по метрикам: среднее за `after` дней со старта против базы = средние тех же дней недели за `before` дней до."""
    s = pd.Timestamp(start)
    pre = df[(df.date >= s - pd.Timedelta(days=before)) & (df.date < s)]
    post = df[(df.date >= s) & (df.date < s + pd.Timedelta(days=after))]
    if len(pre) < before or len(post) < after:
        return None
    out = {"start": s, "pre_n": len(pre), "post_n": len(post)}
    for col in ("checks", "avg_check", "net"):
        by_wd = pre.groupby("wd")[col].mean()
        base = post["wd"].map(by_wd).fillna(pre[col].mean())
        out[col + "_base"] = float(base.mean())
        out[col + "_fact"] = float(post[col].mean())
        out[col + "_pct"] = (out[col + "_fact"] / out[col + "_base"] - 1) * 100
    return out


def noise_band(df: pd.DataFrame, before: int = 14, after: int = 7, skip: list | None = None) -> dict:
    """Тот же Δ% на каждой дате старта: что такое «обычное» колебание без акции (10-й и 90-й перцентили)."""
    skip = skip if skip is not None else [e["start"] for e in EVENTS]
    res = {"checks": [], "avg_check": [], "net": []}
    for s in df.date.iloc[before: len(df) - after + 1]:
        if any(abs((s - pd.Timestamp(k)).days) < after for k in skip):
            continue
        e = effect(df, s.isoformat(), before, after)
        if e:
            for c in res:
                res[c].append(e[c + "_pct"])
    return {c: (float(np.percentile(v, 10)), float(np.percentile(v, 90))) if v else (0.0, 0.0) for c, v in res.items()}


def verdict(pct: float, band: tuple) -> str:
    lo, hi = band
    return "up" if pct > hi else "down" if pct < lo else "flat"


def _num(x) -> float | None:
    """Первое число из ячейки прогноза ('15 (позже 14)' -> 15, 'x4' -> None)."""
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return None
    m = re.match(r"^\s*(\d+(?:[.,]\d+)?)", str(x))
    return float(m.group(1).replace(",", ".")) if m else None


def breakeven_table() -> pd.DataFrame:
    """Акции доставки с прогнозом маркетинга: нужен ли прирост продаж позиции, чтобы скидка РЕСТОРАНА окупилась по марже."""
    _, d = load_calendar()
    fc = food_cost_ratio()
    rows = []
    for _, r in d.iterrows():
        orig, rest = r["Цена обычная, ₸"], r["Цена для ресторана, ₸"]
        forecast = _num(r["Прогноз прироста, %"])
        rd = 1 - rest / orig
        if forecast is None:
            continue
        if rd <= 0.005:
            need, ok, comment = 0.0, True, "скидку платит агрегатор: ресторан не теряет в цене"
        elif (1 - rd) <= fc:
            need, ok, comment = float("inf"), False, "после скидки цена ниже себестоимости"
        else:
            need = ((1 - fc) / ((1 - rd) - fc) - 1) * 100
            ok = forecast >= need
            comment = "окупается по марже" if ok else "по марже не окупается (может окупиться новыми гостями и допродажами)"
        rows.append({"platform": r["Платформа"], "period": r["Период"], "item": r["Позиция"], "price": orig,
                     "restaurant_discount_pct": round(rd * 100, 1), "guest_discount_pct": r["Скидка гостю, %"],
                     "marketing_forecast_uplift_pct": forecast, "breakeven_uplift_pct": round(need, 1),
                     "pays_off": bool(ok), "comment": comment})
    return pd.DataFrame(rows)


def promo_history(promo: str, before: int = 14, after: int = 7) -> dict:
    """Факт по одной прошлой акции из списка EVENTS (id или часть названия)."""
    ev = event_by_id(promo)
    if ev is None:
        return {"error": f"неизвестная акция '{promo}'. Доступные: " + "; ".join(f"{e['id']} ({e['name']})" for e in EVENTS)}
    df = load_daily()
    e = effect(df, ev["start"], before, after)
    if not e:
        return {"error": "для этой даты не хватает дней до/после в данных"}
    band = noise_band(df, before, after)
    v = {k: verdict(e[k + "_pct"], band[k]) for k in ("checks", "avg_check", "net")}
    be = breakeven_table()
    return {
        "scenario": {"type": "promo_history", "promo_id": ev["id"], "name": ev["name"], "start": ev["start"],
                     "channel": ev["channel"], "guest_discount_pct": ev["guest_discount"], "funded_by": ev["funded_by"],
                     "note": ev["note"]},
        "econometric": {
            "checks_per_day_before": round(e["checks_base"]), "checks_per_day_after": round(e["checks_fact"]),
            "checks_delta_pct": round(e["checks_pct"], 1),
            "avg_check_before": round(e["avg_check_base"]), "avg_check_after": round(e["avg_check_fact"]),
            "avg_check_delta_pct": round(e["avg_check_pct"], 1),
            "revenue_per_day_delta": round(e["net_fact"] - e["net_base"]), "revenue_delta": round(e["net_fact"] - e["net_base"]),
            "revenue_delta_pct": round(e["net_pct"], 1),
        },
        "verdict": {"checks": v["checks"], "avg_check": v["avg_check"], "revenue": v["net"]},
        "normal_fluctuation_pct": {k: [round(band[k][0], 1), round(band[k][1], 1)] for k in band},
        "window": {"days_before": before, "days_after": after},
        "caveat": "акции шли внахлёст, сезонность не отделена; нужны продажи по позициям по дням",
        "breakeven_same_channel": be[be.platform.str.startswith(ev["channel"])].head(6).to_dict("records") if ev["channel"] != "Ресторан" else [],
    }


FUNDING = ["ресторан", "пополам", "агрегатор"]
DEFAULT_FUNDING = {"Yandex": "пополам", "Wolt": "пополам", "Glovo": "агрегатор", "Ресторан": "ресторан"}


def restaurant_share(funded_by: str) -> float:
    """Какую долю скидки гостю оплачивает ресторан (в письмах Yandex/Wolt скидка гостю 40% = цена ресторана −20%)."""
    f = str(funded_by).lower()
    return 1.0 if f.startswith("рест") else 0.5 if f.startswith("попол") else 0.0


def forecast_promo(channel: str = "Yandex", guest_discount_pct: float = 30, funded_by: str = "",
                   duration_days: int = 14, before: int = 14, after: int = 7) -> dict:
    """Ориентир эффекта новой акции по аналогам: тот же канал и похожая глубина скидки. Не прогноз."""
    ch = next((c for c in CHANNELS if c.lower() == str(channel).strip().lower()), None)
    if ch is None:
        return {"error": f"канал '{channel}' неизвестен, доступные: {', '.join(CHANNELS)}"}
    guest_discount_pct = float(guest_discount_pct)
    funded_by = funded_by or DEFAULT_FUNDING[ch]
    df = load_daily()
    band = noise_band(df, before, after)
    analogs = []
    for ev in EVENTS:
        e = effect(df, ev["start"], before, after)
        if not e:
            continue
        w = (2.0 if ev["channel"] == ch else 1.0) / (1 + abs(ev["guest_discount"] - guest_discount_pct) / 10)
        analogs.append({"id": ev["id"], "name": ev["name"], "channel": ev["channel"], "guest_discount_pct": ev["guest_discount"],
                        "checks_pct": round(e["checks_pct"], 1), "avg_check_pct": round(e["avg_check_pct"], 1),
                        "net_pct": round(e["net_pct"], 1), "weight": round(w, 3)})
    same = [a for a in analogs if a["channel"] == ch]
    pool = same if same else analogs
    wsum = sum(a["weight"] for a in pool)
    mean = {k: sum(a[k] * a["weight"] for a in pool) / wsum for k in ("checks_pct", "avg_check_pct", "net_pct")}
    lo = {k: min(a[k] for a in pool) for k in mean}
    hi = {k: max(a[k] for a in pool) for k in mean}
    last = df.tail(28)
    base_checks, base_avg = float(last.checks.median()), float(last.avg_check.median())
    base_rev = base_checks * base_avg
    rd_pct = guest_discount_pct * restaurant_share(funded_by)
    fc = food_cost_ratio()
    be = None
    if rd_pct > 0:
        r = rd_pct / 100
        be = round(((1 - fc) / ((1 - r) - fc) - 1) * 100, 1) if (1 - r) > fc else float("inf")
    return {
        "scenario": {"type": "promo", "name": f"{ch}: скидка {guest_discount_pct:.0f}% гостю", "channel": ch,
                     "guest_discount_pct": guest_discount_pct, "funded_by": funded_by, "duration_days": int(duration_days)},
        "econometric": {
            "baseline_checks_per_day": round(base_checks), "baseline_avg_check": round(base_avg),
            "baseline_revenue_per_day": round(base_rev),
            "checks_delta_pct": round(mean["checks_pct"], 1), "checks_delta_range_pct": [round(lo["checks_pct"], 1), round(hi["checks_pct"], 1)],
            "avg_check_delta_pct": round(mean["avg_check_pct"], 1),
            "revenue_delta_pct": round(mean["net_pct"], 1), "revenue_delta_range_pct": [round(lo["net_pct"], 1), round(hi["net_pct"], 1)],
            "revenue_delta": round(base_rev * mean["net_pct"] / 100),
            "revenue_delta_range": [round(base_rev * lo["net_pct"] / 100), round(base_rev * hi["net_pct"] / 100)],
            "revenue_delta_period": round(base_rev * mean["net_pct"] / 100 * int(duration_days)),
            "restaurant_discount_pct": rd_pct,
            "breakeven_item_uplift_pct": be,
            "food_cost_ratio_assumed": round(fc, 2),
        },
        "normal_fluctuation_pct": {k: [round(band[k][0], 1), round(band[k][1], 1)] for k in band},
        "analogs": sorted(analogs, key=lambda a: -a["weight"]),
        "analogs_used": "тот же канал" if same else "все акции (в этом канале аналогов нет)",
        "analogs_n": len(pool),
        "caveat": ("ориентир по аналогам из истории: эффект измерен по первой неделе, на общих чеках ресторана, "
                   "акции шли внахлёст. Для срока длиннее недели и по позициям не проверено."),
    }