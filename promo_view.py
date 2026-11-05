# python 3.10+, streamlit/plotly: promo analytics tab (history -> payback -> new promo what-if), logic lives in promo_engine.py
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import promo_engine as pe
from promo_engine import EVENTS, effect, noise_band, verdict
from report import generate_report

HOURLY = pe.DATA / "real_deluxe_by_hour.csv"
GOOD, BAD, GREY, BLUE = "#10b981", "#ef4444", "#94a3b8", "#3b82f6"
load_daily = st.cache_data(pe.load_daily.__wrapped__)
load_calendar = st.cache_data(pe.load_calendar.__wrapped__)


def timeline_fig(inside: pd.DataFrame, deliv: pd.DataFrame) -> go.Figure:
    rows = []
    for _, r in deliv.iterrows():
        per = str(r["Период"]).split()[0].replace("–", "-")
        try:
            a, b = per.split("-")
            a = pd.to_datetime(a + ".2026", format="%d.%m.%Y"); b = pd.to_datetime(b + ".2026", format="%d.%m.%Y")
        except Exception:
            continue
        rows.append(dict(start=a, end=b + pd.Timedelta(days=1), ch=r["Платформа"].split()[0], pos=r["Позиция"], disc=r["Скидка гостю, %"]))
    tl = pd.DataFrame(rows)
    fig = go.Figure()
    colors = {"Yandex": "#f59e0b", "Glovo": "#10b981", "Wolt": "#3b82f6", "Wolt+": "#8b5cf6"}
    for ch, g in tl.groupby("ch"):
        for _, r in g.iterrows():
            fig.add_trace(go.Bar(base=[r.start], x=[(r.end - r.start).total_seconds() * 1000], y=[ch], orientation="h",
                                 marker=dict(color=colors.get(ch, GREY), line=dict(color="white", width=.5)), opacity=.55,
                                 hovertemplate=f"{r.pos}<br>−{r.disc:.0f}% гостю<extra>{ch}</extra>", showlegend=False))
    inn = {"Рамадан Сет": ("2026-02-19", "2026-03-19"), "Breakfast Box": ("2026-05-13", "2026-06-30"),
           "Летнее промо": ("2026-05-28", "2026-09-30"), "I'M CUP": ("2026-07-08", "2026-09-30"),
           "Coca-Cola подарки": ("2026-07-08", "2026-07-19"), "Осеннее промо": ("2026-10-15", "2026-11-05"),
           "Стрипсы": ("2026-10-15", "2026-11-05")}
    for n, (a, b) in inn.items():
        fig.add_trace(go.Bar(base=[pd.Timestamp(a)], x=[(pd.Timestamp(b) - pd.Timestamp(a)).total_seconds() * 1000], y=[n], orientation="h",
                             marker=dict(color="#ef4444", line=dict(color="white", width=.5)), opacity=.7, showlegend=False,
                             hovertemplate=f"{n}<br>{a} - {b}<extra></extra>"))
    fig.add_vrect(x0="2026-06-01", x1="2026-08-31", fillcolor="#10b981", opacity=.07, line_width=0,
                  annotation_text="есть данные продаж", annotation_position="top left")
    fig.update_layout(barmode="overlay", xaxis_type="date", height=430, margin=dict(l=0, r=0, t=30, b=0),
                      title="Календарь промо 2026: ресторан (красный) и доставка по платформам")
    return fig


VERSION = "v4"
CSS = """
<style>
.pv-kpis{display:flex;gap:14px;flex-wrap:wrap;margin:6px 0 14px}
.pv-kpi{flex:1;min-width:180px;padding:14px 18px;border-radius:12px;background:rgba(128,128,128,.08);border:1px solid rgba(128,128,128,.25)}
.pv-kpi small{display:block;opacity:.65;font-size:12px}.pv-kpi b{font-size:26px}
.pv-card{padding:16px 18px;border-radius:14px;border:1px solid rgba(128,128,128,.3);background:rgba(128,128,128,.06);margin:0 0 14px;min-height:190px}
.pv-top{display:flex;align-items:center;gap:10px;margin-bottom:6px}
.pv-num{width:30px;height:30px;border-radius:50%;background:#f59e0b;color:#111;font-weight:700;display:flex;align-items:center;justify-content:center;flex:none}
.pv-title{font-size:16px;font-weight:600;line-height:1.25}
.pv-meta{font-size:12.5px;opacity:.65;margin-bottom:10px}
.pv-big{font-size:19px;font-weight:700;margin:6px 0}
.pv-up{color:#10b981}.pv-down{color:#ef4444}.pv-flat{color:#94a3b8}
.pv-nums{display:flex;gap:18px;font-size:13px;opacity:.85;margin-top:8px}
.pv-nums b{display:block;font-size:16px}
.pv-foot{font-size:13px;opacity:.7;line-height:1.5;margin-top:4px}
</style>
"""


TEXT = {"up": ("🟢", "Гостей стало больше: похоже, акция сработала"),
        "down": ("🔴", "Гостей стало меньше обычного"),
        "flat": ("⚪", "Заметных изменений нет")}


def daily_chart(df: pd.DataFrame, marks: list[tuple[int, str]]) -> go.Figure:
    fig = go.Figure(go.Scatter(x=df.date, y=df.checks.rolling(7, min_periods=3).mean(), mode="lines",
                               line=dict(color=BLUE, width=3), hovertemplate="%{x|%d.%m}: %{y:.0f} гостей<extra></extra>"))
    for n, d in marks:
        x = pd.Timestamp(d)
        fig.add_vline(x=x, line=dict(color="#f59e0b", width=1.5, dash="dot"))
        fig.add_annotation(x=x, y=1.0, yref="paper", text=f"<b>{n}</b>", showarrow=False, yanchor="bottom",
                           bgcolor="#f59e0b", font=dict(color="#111", size=13), borderpad=4)
    fig.update_layout(height=320, margin=dict(l=0, r=0, t=34, b=0), yaxis_title="гостей в день", showlegend=False,
                      yaxis=dict(rangemode="tozero"))
    return fig


def card(n: int, name: str, start: str, note: str, e: dict, v: str) -> str:
    icon, text = TEXT[v]
    return (f'<div class="pv-card"><div class="pv-top"><div class="pv-num">{n}</div><div class="pv-title">{name}</div></div>'
            f'<div class="pv-meta">старт {pd.Timestamp(start):%d.%m} · {note}</div>'
            f'<div class="pv-big pv-{v}">{icon} {text}</div>'
            f'<div class="pv-nums"><div>Гостей в день<b>{e["checks_base"]:.0f} → {e["checks_fact"]:.0f}</b>{e["checks_pct"]:+.1f}%</div>'
            f'<div>Средний чек<b>{e["avg_check_base"]:,.0f} → {e["avg_check_fact"]:,.0f}</b>{e["avg_check_pct"]:+.1f}%</div>'
            f'<div>Выручка в день<b>{e["net_pct"]:+.1f}%</b>&nbsp;</div></div></div>')


EXTRA_CSS = """
<style>
.pv-note{font-size:14px;line-height:1.55;padding:12px 16px;border-radius:10px;background:rgba(59,130,246,.10);border:1px solid rgba(59,130,246,.30);margin:4px 0 12px}
table.pv-t{width:100%;border-collapse:collapse;font-size:14px}
table.pv-t th{text-align:left;font-size:12px;opacity:.65;font-weight:500;padding:6px 8px;border-bottom:1px solid rgba(128,128,128,.3)}
table.pv-t td{padding:8px;border-bottom:1px solid rgba(128,128,128,.15)}
.pv-pill{display:inline-block;padding:2px 10px;border-radius:999px;font-size:12.5px;font-weight:600;white-space:nowrap}
.pv-pill.ok{background:rgba(16,185,129,.2);color:#10b981}.pv-pill.no{background:rgba(239,68,68,.18);color:#ef4444}.pv-pill.na{background:rgba(148,163,184,.25);color:#94a3b8}
.pv-res{padding:18px 22px;border-radius:14px;border:1px solid rgba(59,130,246,.45);background:rgba(59,130,246,.08);margin:8px 0 12px}
.pv-res h3{margin:0 0 6px;font-size:20px}
</style>
"""


def render_promo_result(result: dict, key: str = "promo") -> None:
    """Результат simulate_promo: общий вид для вкладки промо и вкладки «Сценарий»."""
    sc, e = result["scenario"], result["econometric"]
    lo, hi = e["revenue_delta_range"]
    be = e.get("breakeven_item_uplift_pct")
    be_txt = ("Скидку платит агрегатор: ресторан в цене не теряет (комиссии и условия договора не учтены)." if be is None else
              f"Ресторан отдаёт {e['restaurant_discount_pct']:.0f}% цены. Чтобы скидка окупилась по марже, продажи акционных позиций "
              f"должны вырасти минимум на <b>{be}%</b> (себестоимость принята {e['food_cost_ratio_assumed'] * 100:.0f}% цены).")
    st.markdown(
        f'<div class="pv-res"><h3>{sc["name"]} · {sc["duration_days"]} дн. · платит: {sc["funded_by"]}</h3>'
        f'<div class="pv-line">Гостей в день: <b>{e["checks_delta_pct"]:+.1f}%</b> '
        f'(аналоги: {e["checks_delta_range_pct"][0]:+.1f}…{e["checks_delta_range_pct"][1]:+.1f}%)<br>'
        f'Выручка в день: <b>{e["revenue_delta"]:+,.0f} ₸</b> ({lo:+,.0f}…{hi:+,.0f}), за период около <b>{e["revenue_delta_period"]:+,.0f} ₸</b><br>'
        f'{be_txt}</div>'
        f'<div class="pv-sub" style="margin-top:8px">Опора: {result["analogs_n"]} акций из истории ({result["analogs_used"]}). {result["caveat"]}</div></div>',
        unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    an = result["analogs"]
    fig = go.Figure(go.Bar(x=[a["checks_pct"] for a in an], y=[f'{a["name"].split(":")[0]} {a["id"][-5:]}' for a in an], orientation="h",
                           marker_color=[GOOD if a["checks_pct"] >= 0 else BAD for a in an],
                           text=[f'{a["checks_pct"]:+.1f}%' for a in an], textposition="outside", cliponaxis=False))
    pad = max(abs(a["checks_pct"]) for a in an) * .3 or 1
    fig.update_xaxes(range=[min(0, *[a["checks_pct"] for a in an]) - pad, max(0, *[a["checks_pct"] for a in an]) + pad])
    fig.update_layout(title="Δ гостей после прошлых акций, % (в расчёт взяты акции того же канала)", height=290, margin=dict(l=0, r=30, t=50, b=0),
                      yaxis=dict(autorange="reversed"))
    c1.plotly_chart(fig, use_container_width=True, key=f"{key}_an")
    per = result.get("persona_simulation")
    if per:
        vals = [per["accept_pct"], per["switch_pct"], per["leave_pct"]]
        pie = go.Figure(go.Pie(labels=per.get("labels"), values=vals, hole=.55, sort=False, textinfo="text",
                               text=[f"{v}%" if v else "" for v in vals], marker=dict(colors=[GOOD, "#f59e0b", GREY])))
        pie.update_layout(title="Реакция 15 AI-персон гостей", height=290, margin=dict(l=0, r=0, t=50, b=0))
        c2.plotly_chart(pie, use_container_width=True, key=f"{key}_pp")
    if st.button("📄 Сгенерировать отчёт по акции", key=f"{key}_rep"):
        if st.session_state.get("mirofish_result", {}).get("ok"):
            result = {**result, "mirofish": st.session_state["mirofish_result"]}
        path = generate_report(result)
        st.success(f"Отчёт сохранён: {path}")
        st.download_button("Скачать отчёт", path.read_text(encoding="utf-8"), file_name=path.name, key=f"{key}_dl")


def payback_table() -> str:
    b = pe.breakeven_table()
    b = b[b.restaurant_discount_pct > 0].drop_duplicates(["platform", "item", "marketing_forecast_uplift_pct"])
    rows = []
    for _, r in b.iterrows():
        cls, txt = ("ok", "окупается") if r.pays_off else ("no", "не окупается по марже")
        rows.append(f"<tr><td>{r.platform}</td><td>{r['item']}</td><td>{r.restaurant_discount_pct:.0f}%</td>"
                    f"<td>+{r.marketing_forecast_uplift_pct:.0f}%</td><td>+{r.breakeven_uplift_pct:.0f}%</td>"
                    f'<td><span class="pv-pill {cls}">{txt}</span></td></tr>')
    return ('<table class="pv-t"><tr><th>Платформа</th><th>Позиция</th><th>Скидка ресторана к цене</th><th>Прогноз маркетинга</th>'
            f'<th>Нужно для окупаемости</th><th>Итог</th></tr>{"".join(rows)}</table>')


def render() -> None:
    st.subheader("📣 Промо-аналитика: сработали ли акции и что запускать дальше")
    st.caption(f"версия экрана {VERSION} · Dostyk Plaza, 01.06–31.08.2026, реальные продажи iiko; календарь промо и цены из писем и гайдов")
    if not pe.DAILY.exists() or not pe.CAL.exists():
        st.warning("Нет файлов data/real_daily_revenue.csv или data/promo_calendar.xlsx.")
        return
    st.markdown(CSS + EXTRA_CSS, unsafe_allow_html=True)
    df, (inside, deliv) = load_daily(), load_calendar()
    with st.expander("Настройки сравнения"):
        a, b = st.columns(2)
        before = a.slider("Сколько дней «до» акции сравнивать", 7, 21, 14)
        after = b.slider("Сколько дней «после» старта сравнивать", 5, 14, 7)
    band = noise_band(df, before, after)

    st.markdown(
        f'<div class="pv-kpis"><div class="pv-kpi"><small>гостей в день, в среднем</small><b>{df.checks.mean():.0f}</b></div>'
        f'<div class="pv-kpi"><small>средний чек</small><b>{df.net.sum() / df.checks.sum():,.0f} ₸</b></div>'
        f'<div class="pv-kpi"><small>выручка за 92 дня</small><b>{df.net.sum() / 1e6:.0f} млн ₸</b></div>'
        f'<div class="pv-kpi"><small>акций с заметным ростом гостей</small><b>'
        f'{sum(1 for ev in EVENTS if (r := effect(df, ev["start"], before, after)) and verdict(r["checks_pct"], band["checks"]) == "up")} из {len(EVENTS)}</b></div></div>',
        unsafe_allow_html=True)

    st.markdown("### 1. Как сработали прошлые акции")
    st.plotly_chart(daily_chart(df, [(i + 1, ev["start"]) for i, ev in enumerate(EVENTS)]), use_container_width=True)
    st.caption("Синяя линия: сколько гостей приходило в день (среднее за 7 дней). Оранжевые цифры: старты акций, расшифровка в карточках.")
    cols = st.columns(2)
    for i, ev in enumerate(EVENTS):
        e = effect(df, ev["start"], before, after)
        if e:
            cols[i % 2].markdown(card(i + 1, ev["name"], ev["start"], ev["note"], e, verdict(e["checks_pct"], band["checks"])),
                                 unsafe_allow_html=True)
    st.markdown(
        f'<div class="pv-foot"><b>Как читать.</b> «Было → стало» = обычный день за {before} дней до старта (с учётом дня недели) и '
        f'первые {after} дней акции. «Заметных изменений нет» значит: такие колебания бывают и без акций '
        f'(гостей от {band["checks"][0]:+.0f}% до {band["checks"][1]:+.0f}%). Акции шли внахлёст, летом гостей и так становилось больше, '
        f'поэтому это «похоже на эффект», а не доказательство.</div>', unsafe_allow_html=True)

    st.markdown("### 2. Окупаются ли скидки ресторана")
    st.caption("По ценам из писем агрегаторов и прогнозу прироста от маркетинга. Только скидки, которые оплачивает ресторан "
               "(у Glovo скидку платит агрегатор). Себестоимость принята 35% цены.")
    bt = pe.breakeven_table()
    bt = bt[bt.restaurant_discount_pct > 0].drop_duplicates(["platform", "item", "marketing_forecast_uplift_pct"])
    st.markdown(f'<div class="pv-note"><b>Главное:</b> из {len(bt)} скидок, которые платит ресторан, по прогнозу самого маркетинга '
                f'по марже окупаются {int(bt.pays_off.sum())}. Остальные нужны ради новых гостей и допродаж, а не ради маржи с самой позиции. '
                f'Проверить это можно только по продажам позиций по дням.</div>', unsafe_allow_html=True)
    with st.expander(f"Показать все {len(bt)} акций"):
        st.markdown(payback_table(), unsafe_allow_html=True)

    st.markdown("### 3. Что если запустить новую акцию")
    c1, c2, c3, c4 = st.columns([1, 1, 1, 1])
    ch = c1.selectbox("Канал", pe.CHANNELS, index=0, key="pn_channel")
    disc = c2.slider("Скидка гостю, %", 5, 60, 30, step=5, key="pn_disc")
    fund_default = pe.FUNDING.index(pe.DEFAULT_FUNDING[ch])
    fund = c3.selectbox("Кто платит скидку", pe.FUNDING, index=fund_default, key=f"pn_fund_{ch}")
    days = c4.slider("Дней", 3, 30, 14, key="pn_days")
    if st.button("Посчитать акцию", type="primary", key="pn_go"):
        from simulator import simulate_promo
        st.session_state["last_result"] = simulate_promo(ch, disc, fund, days)
    last = st.session_state.get("last_result")
    if last and last.get("scenario", {}).get("type") == "promo":
        render_promo_result(last, key="pv")
        st.caption("Эта же акция теперь доступна на вкладках «Сценарий» (отчёт) и «MiroFish (эксперимент)». "
                   "На вкладке «Спроси агента» можно спросить то же словами.")
    else:
        st.info("Выбери канал и скидку и нажми «Посчитать акцию».")

    with st.expander("Календарь всех промо 2026 года"):
        st.plotly_chart(timeline_fig(inside, deliv), use_container_width=True)
        st.caption("Красный: акции в ресторане. Жёлтый, зелёный, синий, фиолетовый: доставка (Yandex, Glovo, Wolt, Wolt+).")
    with st.expander("Сколько приносят промо-позиции"):
        total = df["net"].sum()
        w1, w2 = st.columns(2)
        w1.metric("Биг Делюкс (I'M CUP)", f"{5_920_350 / total * 100:.1f}% выручки", "5,9 млн ₸ за 01.06–31.08", delta_color="off")
        w1.metric("Летнее промо (6 напитков)", f"{1_431_700 / total * 100:.1f}% выручки", "1,4 млн ₸ за 01.06–31.08", delta_color="off")
        if HOURLY.exists():
            h = pd.read_csv(HOURLY)
            fig = go.Figure(go.Bar(x=h["hour"], y=h["qty"], marker_color="#ef4444"))
            fig.update_layout(title="Биг Делюкс: в какой час покупают, штук", height=260, margin=dict(l=0, r=0, t=50, b=0), xaxis_title="час")
            w2.plotly_chart(fig, use_container_width=True)