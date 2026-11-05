# Menu What-If Report — price_change
_Generated: 2026-11-03T12:43:53_

## Сценарий
```json
{
  "type": "price_change",
  "sku_id": "SKU001",
  "sku_name": "Биф Тейсти",
  "price_delta_pct": 0.1
}
```

## Экономический результат (baseline эластичность)
| Метрика | Значение |
|---|---|
| total_baseline_revenue | 547927.0 |
| total_new_revenue | 548438.0 |
| revenue_delta | 511.0 |
| revenue_delta_pct | 0.09 |
| total_baseline_margin | 356094.0 |
| total_new_margin | 356799.0 |
| margin_delta | 705.0 |
| margin_delta_pct | 0.2 |

## Топ-движения по SKU
| SKU | Название | Δ спрос % | Δ выручка | Δ маржа |
|---|---|---|---|---|
| SKU014 | Биф Биг Делюкс | 1.9% | 215.0 | 140.0 |
| SKU013 | Double Big Burger | 1.9% | 210.0 | 136.0 |
| SKU002 | Дабл Гранд Чизбургер | 1.9% | 204.0 | 133.0 |
| SKU001 | Биф Тейсти | -10.0% | -119.0 | 296.0 |
| SKU003 | Big Burger | 0.0% | 0.0 | 0.0 |

## Реакция AI-персон (MiroFish-style, 15 гостей)
| Метрика | Значение |
|---|---|
| total_personas | 15 |
| accept_pct | 40.0 |
| switch_pct | 33.3 |
| leave_pct | 26.7 |

**Примеры возражений:**
- Budget Student sees the price hike and orders from a competitor instead
- Family with Kids grumbles about the price but picks a cheaper item in the same category
- Price-First Commuter sees the price hike and orders from a competitor instead
- Office Lunch Group grumbles about the price but picks a cheaper item in the same category
- Late-Night Snacker sees the price hike and orders from a competitor instead

## Допущения модели

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
4. **AI-персоны (MiroFish-style)** — 15 синтетических профилей гостей с заданными bias
   (бюджетная чувствительность, лояльность, предпочтения категорий). Их реакция —
   качественный сигнал (разногласия, risk of churn), **не доказательство поведения реальных
   гостей**. Используется как second opinion поверх эконометрики, не как замена.
5. **Baseline продаж** — среднее по 75 дням истории с учётом дня недели, без учёта праздников,
   погоды, маркетинговых акций, конкурентного давления.
