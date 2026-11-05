# python, markdown report exporter with stated assumptions for P03 Menu Simulator
from datetime import datetime
from pathlib import Path
import json

REPORTS_DIR = Path(__file__).parent / "reports"
REPORTS_DIR.mkdir(exist_ok=True)

ASSUMPTIONS = """## Допущения модели

1. **Эластичность спроса** — задана на уровне категории (напр. Burgers: -1.1, Drinks: -1.8),
   не оценена по историческим ценовым вариациям (синтетические данные почти не содержат
   изменения цен). В реальном проекте — заменить на regression-оценку (statsmodels OLS/log-log)
   по факту изменения цен в истории продаж.
2. **Каннибализация** — при удалении/подорожании SKU, 55% потерянного спроса перетекает на
   товары из той же substitute_group (напр. другие бургеры), пропорционально их текущей доле.
   Остальные 45% — чистая потеря (уходят к конкуренту или не покупают вовсе).
3. **Комбо** — attach rate 20% (доля гостей, выбирающих комбо вместо отдельных позиций) и
   bundling uplift +12% (комбо стимулирует часть гостей добавить что-то, что иначе бы не взяли) —
   обе цифры экспертные предположения, требуют A/B теста на реальных данных для калибровки.
4. **AI-персоны** — 15 синтетических профилей гостей с заданными bias
   (бюджетная чувствительность, лояльность, предпочтения категорий). Их реакция —
   качественный сигнал (разногласия, risk of churn), **не доказательство поведения реальных
   гостей**. Используется как second opinion поверх эконометрики, не как замена.
5. **Промо** — эффект новой акции оценивается по аналогам из реальной истории одного ресторана за 92 дня
   (только итоги по дням, акции шли внахлёст), окупаемость скидки ресторана считается по ценам из писем агрегаторов
   и допущению себестоимости 35% цены. Это ориентир для A/B-теста, не прогноз.
6. **Baseline продаж** — среднее по 75 дням истории с учётом дня недели, без учёта праздников,
   погоды, маркетинговых акций, конкурентного давления.
"""


def generate_report(scenario_result: dict, output_name: str = None) -> Path:
    scenario = scenario_result.get("scenario", {})
    econ = scenario_result.get("econometric", {})
    personas = scenario_result.get("persona_simulation", {})
    movers = scenario_result.get("per_sku_top_movers", [])

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = output_name or f"report_{scenario.get('type', 'scenario')}_{ts}.md"
    path = REPORTS_DIR / name

    lines = [
        f"# Menu What-If Report — {scenario.get('type', 'scenario')}",
        f"_Generated: {datetime.now().isoformat(timespec='seconds')}_",
        "",
        "## Сценарий",
        "```json",
        json.dumps(scenario, indent=2, ensure_ascii=False),
        "```",
        "",
        "## Экономический результат (baseline эластичность)",
        "| Метрика | Значение |",
        "|---|---|",
    ]
    for k, v in econ.items():
        lines.append(f"| {k} | {v} |")

    if movers:
        lines += ["", "## Топ-движения по SKU", "| SKU | Название | Δ спрос % | Δ выручка | Δ маржа |", "|---|---|---|---|---|"]
        for m in movers:
            lines.append(f"| {m['sku_id']} | {m['name']} | {m['unit_delta_pct']}% | {m['revenue_delta']} | {m['margin_delta']} |")

    if personas:
        lines += [
            "", "## Реакция AI-персон (15 гостей, каждая реагирует независимо)",
            "| Метрика | Значение |", "|---|---|",
        ]
        for k, v in personas.items():
            if k != "sample_objections":
                lines.append(f"| {k} | {v} |")
        if personas.get("sample_objections"):
            lines += ["", "**Примеры возражений:**"]
            for obj in personas["sample_objections"]:
                lines.append(f"- {obj}")

    if scenario.get("type") in ("promo", "promo_history"):
        lines += ["", "## Опора на реальные данные", "_Dostyk Plaza, 01.06–31.08.2026: эффект акции на общих чеках ресторана; "
                  "акции шли внахлёст, сезонность не отделена._"]
        if scenario_result.get("analogs"):
            lines += ["", f"Аналоги ({scenario_result.get('analogs_used')}):", "| Акция | Канал | Скидка гостю | Δ гостей | Δ чека | Δ выручки |", "|---|---|---|---|---|---|"]
            for a in scenario_result["analogs"]:
                lines.append(f"| {a['name']} | {a['channel']} | {a['guest_discount_pct']}% | {a['checks_pct']}% | {a['avg_check_pct']}% | {a['net_pct']}% |")
        if scenario_result.get("normal_fluctuation_pct"):
            lines += ["", f"Обычные колебания без акций (10–90 перцентиль): {scenario_result['normal_fluctuation_pct']}"]
        if scenario_result.get("caveat"):
            lines += ["", f"**Оговорка:** {scenario_result['caveat']}"]

    mf = scenario_result.get("mirofish")
    if mf and mf.get("ok"):
        lines += ["", f"## Эксперимент: симуляция MiroFish ({mf.get('rounds')} раундов, {mf.get('elapsed_s')} с)",
                  "_Качественное второе мнение мультиагентной симуляции. Не влияет на цифры выше и не является "
                  "доказательством поведения реальных гостей._", "", mf.get("report_markdown", "")]

    lines += ["", ASSUMPTIONS]

    path.write_text("\n".join(lines), encoding="utf-8")
    return path


if __name__ == "__main__":
    from simulator import simulate_price_change
    result = simulate_price_change("SKU001", 0.10)
    path = generate_report(result)
    print(f"report written -> {path}")