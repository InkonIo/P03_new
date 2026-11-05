# python, streamlit UI for P03 Menu Simulator
import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from elasticity import load_data
from simulator import simulate_price_change, simulate_removal, simulate_combo
from agent_trace import run_agent, EXAMPLES
import agent_view
from report import generate_report
import mirofish_adapter

st.set_page_config(page_title="Menu What-If Simulator", layout="wide")
st.title("🍔 Menu What-If Simulator — P03")
st.caption("Симуляция изменения цен, комбо, удаления SKU и каннибализации спроса")

menu, sales = load_data()
combos = pd.read_csv("data/combos.csv")

tab_scenario, tab_agent, tab_mf, tab_data = st.tabs(["📊 Сценарий", "🤖 Спроси агента", "🧪 MiroFish (эксперимент)", "📋 Данные"])

with tab_scenario:
    col_left, col_right = st.columns([1, 2])

    with col_left:
        scenario_type = st.radio("Тип изменения", ["Изменение цены", "Удаление SKU", "Комбо"])

        if scenario_type == "Изменение цены":
            sku_name = st.selectbox("SKU", menu["name"].tolist())
            sku_id = menu[menu.name == sku_name].iloc[0]["sku_id"]
            pct = st.slider("Изменение цены, %", -30, 30, 10, step=5)
            run = st.button("Запустить симуляцию", type="primary")
            if run:
                result = simulate_price_change(sku_id, pct / 100)

        elif scenario_type == "Удаление SKU":
            sku_name = st.selectbox("SKU", menu["name"].tolist())
            sku_id = menu[menu.name == sku_name].iloc[0]["sku_id"]
            run = st.button("Запустить симуляцию", type="primary")
            if run:
                result = simulate_removal(sku_id)

        else:
            combo_name = st.selectbox("Комбо", combos["name"].tolist())
            combo_id = combos[combos.name == combo_name].iloc[0]["combo_id"]
            run = st.button("Запустить симуляцию", type="primary")
            if run:
                result = simulate_combo(combo_id)

    with col_right:
        if "run" in dir() and run and "result" in dir():
            st.session_state["last_result"] = result

        if "last_result" in st.session_state:
            result = st.session_state["last_result"]
            econ = result.get("econometric", {})
            personas = result.get("persona_simulation", {})

            c1, c2, c3 = st.columns(3)
            rev_delta = econ.get("revenue_delta", 0)
            margin_delta = econ.get("margin_delta", 0)
            c1.metric("Δ Выручка/день", f"{rev_delta:,.0f} ₸", f"{econ.get('revenue_delta_pct', 0)}%")
            c2.metric("Δ Маржа/день", f"{margin_delta:,.0f} ₸", f"{econ.get('margin_delta_pct', 0)}%")
            c3.metric("Уйдут / переключатся", f"{personas.get('leave_pct', 0)}% / {personas.get('switch_pct', 0)}%")

            if "total_baseline_revenue" in econ:
                fig = go.Figure(data=[
                    go.Bar(name="До", x=["Выручка", "Маржа"], y=[econ["total_baseline_revenue"], econ["total_baseline_margin"]]),
                    go.Bar(name="После", x=["Выручка", "Маржа"], y=[econ["total_new_revenue"], econ["total_new_margin"]]),
                ])
                fig.update_layout(barmode="group", title="До / После, ₸ в день")
                st.plotly_chart(fig, use_container_width=True)

            if result.get("per_sku_top_movers"):
                st.subheader("Топ-движения по SKU")
                st.dataframe(pd.DataFrame(result["per_sku_top_movers"]), use_container_width=True)

            if personas.get("sample_objections"):
                st.subheader("Реакция AI-персон гостей")
                for obj in personas["sample_objections"]:
                    st.write(f"- {obj}")

            if st.button("📄 Сгенерировать отчёт"):
                if st.session_state.get("mirofish_result", {}).get("ok"):
                    result = {**result, "mirofish": st.session_state["mirofish_result"]}
                path = generate_report(result)
                st.success(f"Отчёт сохранён: {path}")
                st.download_button("Скачать отчёт", path.read_text(encoding="utf-8"), file_name=path.name)
        else:
            st.info("Настрой сценарий слева и нажми «Запустить симуляцию»")

with tab_agent:
    st.subheader("🤖 Агент-аналитик: спроси словами и посмотри, как он думает")
    st.caption("Один агент с тремя инструментами (цена, удаление позиции, комбо). Он сам выбирает инструмент, "
               "расчёт делает наш код, агент только решает и объясняет. Каждый шаг виден ниже.")
    agent_view.show_html(st, agent_view.CSS)

    def _pick(text):
        st.session_state["agent_q"] = text
        st.session_state["agent_go"] = True

    first_sku = menu["name"].iloc[0]
    first_combo = combos["name"].iloc[0]
    ex_cols = st.columns(len(EXAMPLES))
    for i, tpl in enumerate(EXAMPLES):
        text = tpl.format(sku=first_sku, combo=first_combo)
        ex_cols[i].button(text, key=f"ex{i}", on_click=_pick, args=(text,), use_container_width=True)

    in_col, btn_col = st.columns([5, 1])
    question = in_col.text_input("Вопрос", key="agent_q", label_visibility="collapsed",
                                 placeholder=f"Например: что если поднять цену на {first_sku} на 15%?")
    go_click = btn_col.button("Спросить", type="primary", use_container_width=True)
    show_think = st.checkbox("Показывать размышления модели (нужен ключ Anthropic)", value=True)
    go = (go_click or st.session_state.pop("agent_go", False)) and bool(question.strip())

    if go:
        flow_ph = st.empty()
        left, right = st.columns([3, 2])
        left.markdown("##### 🧠 Как думает агент")
        tl_ph, side_ph, ans_ph = left.empty(), right.empty(), st.empty()

        def on_step(run):
            agent_view.show_html(flow_ph, agent_view.pipeline_html(run))
            agent_view.show_html(tl_ph, agent_view.timeline_html(run, show_think))
            if run.result and run.steps[-1].kind == "tool_result":
                with side_ph.container():
                    agent_view.render_result_panel(run.result)

        run = run_agent(question.strip(), on_step=on_step, use_thinking=show_think)
        st.session_state["agent_run"] = run
        with ans_ph.container(border=True):
            st.markdown("##### ✅ Ответ агента")
            st.markdown(run.answer)
            st.caption(agent_view.stats_caption(run))
    elif "agent_run" in st.session_state:
        run = st.session_state["agent_run"]
        agent_view.show_html(st, agent_view.pipeline_html(run))
        left, right = st.columns([3, 2])
        left.markdown("##### 🧠 Как думал агент")
        agent_view.show_html(left, agent_view.timeline_html(run, show_think))
        if run.result:
            with right:
                agent_view.render_result_panel(run.result)
        with st.container(border=True):
            st.markdown("##### ✅ Ответ агента")
            st.markdown(run.answer)
            st.caption(agent_view.stats_caption(run))
    else:
        st.info("Выбери пример выше или напиши свой вопрос.")

with tab_mf:
    st.subheader("MiroFish: мультиагентная симуляция (экспериментально)")
    st.caption("Агенты-гости обсуждают изменение меню в симулированной соцсети, затем ReportAgent пишет отчёт. "
               "Это качественное второе мнение: на выручку и маржу не влияет и не доказывает поведение реальных гостей.")
    ok, info = mirofish_adapter.is_available()
    if ok:
        st.success(f"MiroFish доступен: {mirofish_adapter.MIROFISH_URL}")
    else:
        st.warning(f"MiroFish не отвечает ({info}). Запусти его по инструкции в README (раздел MiroFish) "
                   f"или задай MIROFISH_URL.")
    base = st.session_state.get("last_result")
    if not base:
        st.info("Сначала запусти сценарий на вкладке «Сценарий».")
    else:
        st.write("Сценарий:", base.get("scenario", {}))
        rounds = st.slider("Раундов симуляции", 3, 40, 8,
                           help="Авторы MiroFish советуют начинать с <40: расход токенов LLM большой.")
        st.caption("Время: обычно 10-30 минут. Стоимость зависит от модели LLM в .env MiroFish.")
        if st.button("Запустить MiroFish", type="primary", disabled=not ok):
            box = st.empty()
            def cb(stage, d):
                box.info(f"Этап: {stage} · {d.get('status') or d.get('runner_status')} · "
                         f"{d.get('progress', d.get('progress_percent', ''))}%")
            res = mirofish_adapter.run_mirofish(base, max_rounds=rounds, progress_cb=cb)
            st.session_state["mirofish_result"] = res
            box.empty()
        res = st.session_state.get("mirofish_result")
        if res and res.get("ok"):
            st.success(f"Готово за {res['elapsed_s']} с, раундов: {res['rounds']}")
            st.markdown(res["report_markdown"])
            st.caption("Отчёт MiroFish на английском: язык интерфейса бэкенда поддерживает только en/zh. "
                       "Он попадёт в экспортируемый отчёт при нажатии «Сгенерировать отчёт» на вкладке «Сценарий».")
        elif res:
            st.error(f"Ошибка на этапе «{res.get('stage')}»: {res.get('error')}")

with tab_data:
    st.subheader("Меню")
    st.dataframe(menu, use_container_width=True)
    st.subheader("Комбо")
    st.dataframe(combos, use_container_width=True)
    st.subheader("История продаж (последние 200 строк)")
    st.dataframe(sales.tail(200), use_container_width=True)