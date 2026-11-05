# python 3.10+, streamlit visuals for the agent trace: pipeline pills, timeline of steps, result panels
import html
import json

import plotly.graph_objects as go
import streamlit as st

from agent_trace import AgentRun

KIND_STYLE = {   # kind: (цвет, иконка)
    "question": ("#64748b", "?"),
    "thinking": ("#8b5cf6", "💭"),
    "thought": ("#8b5cf6", "💡"),
    "tool_call": ("#3b82f6", "🔧"),
    "tool_result": ("#10b981", "📊"),
    "answer": ("#f59e0b", "✍"),
    "error": ("#ef4444", "!"),
}
STAGES = [("question", "Вопрос"), ("think", "Размышление"), ("tool_call", "Инструмент"),
          ("tool_result", "Результат"), ("answer", "Ответ")]
STAGE_OF = {"question": "question", "thinking": "think", "thought": "think", "tool_call": "tool_call",
            "tool_result": "tool_result", "answer": "answer", "error": "think"}

CSS = """
<style>
.ag-flow{display:flex;gap:6px;flex-wrap:wrap;margin:2px 0 16px}
.ag-pill{padding:5px 14px;border-radius:999px;font-size:13px;border:1px solid rgba(128,128,128,.35);opacity:.5}
.ag-pill.done{opacity:1;border-color:#10b981;color:#10b981}
.ag-pill.cur{opacity:1;border-color:#3b82f6;color:#3b82f6;animation:ag-pulse 1.1s ease-in-out infinite}
@keyframes ag-pulse{0%,100%{box-shadow:0 0 0 0 rgba(59,130,246,.45)}50%{box-shadow:0 0 0 6px rgba(59,130,246,0)}}
@keyframes ag-in{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
.ag-tl{position:relative;margin:4px 0 0 16px;padding-left:24px;border-left:2px solid rgba(128,128,128,.3)}
.ag-step{position:relative;margin:0 0 14px;padding:10px 14px;border-radius:10px;
 background:rgba(128,128,128,.08);border:1px solid rgba(128,128,128,.22);border-left:3px solid var(--c)}
.ag-step.new{animation:ag-in .35s ease-out}
.ag-step:before{content:attr(data-ic);position:absolute;left:-40px;top:8px;width:28px;height:28px;border-radius:50%;
 display:flex;align-items:center;justify-content:center;background:var(--c);color:#fff;font-size:14px;font-weight:700}
.ag-h{display:flex;justify-content:space-between;gap:10px;align-items:baseline}
.ag-h b{font-size:14px}
.ag-t{font-size:12px;opacity:.6;white-space:nowrap}
.ag-b{margin-top:6px;font-size:13.5px;line-height:1.5;opacity:.92}
.ag-think{font-style:italic;opacity:.8;border-left:2px solid rgba(139,92,246,.5);padding-left:10px;margin-top:6px;font-size:13px;line-height:1.5}
.ag-chips{display:flex;gap:6px;flex-wrap:wrap;margin-top:6px}
.ag-chip{font-family:ui-monospace,Menlo,monospace;font-size:12px;padding:2px 9px;border-radius:6px;
 background:rgba(59,130,246,.14);border:1px solid rgba(59,130,246,.35)}
.ag-kpi{display:flex;gap:18px;flex-wrap:wrap;margin-top:6px}
.ag-kpi div{font-size:12px;opacity:.75}
.ag-kpi b{display:block;font-size:16px;opacity:1}
.ag-pos{color:#10b981}.ag-neg{color:#ef4444}
.ag-step details{margin-top:6px;font-size:12px}
.ag-step summary{cursor:pointer;opacity:.7}
.ag-step pre{margin:6px 0 0;padding:8px;border-radius:6px;background:rgba(128,128,128,.12);overflow:auto;max-height:240px;font-size:11.5px}
.ag-live{font-size:13px;opacity:.7;margin:0 0 8px 40px}
.ag-live:after{content:'';display:inline-block;width:6px;height:6px;margin-left:6px;border-radius:50%;background:#3b82f6;animation:ag-pulse 1s infinite}
</style>
"""


def show_html(container, body: str) -> None:
    """st.html (без markdown-парсера) если есть, иначе markdown с unsafe_allow_html."""
    if hasattr(container, "html"):
        container.html(body)
    else:
        container.markdown(body, unsafe_allow_html=True)


def _e(text) -> str:
    return html.escape(str(text)).replace("\n", "<br>")


def _signed(v: float, unit: str = " ₸") -> str:
    cls = "ag-pos" if v > 0 else "ag-neg" if v < 0 else ""
    return f'<span class="{cls}">{v:+,.0f}{unit}</span>'


def pipeline_html(run: AgentRun) -> str:
    seen = [STAGE_OF[s.kind] for s in run.steps]
    last = seen[-1] if seen else None
    pills = []
    for key, label in STAGES:
        if run.done and key in seen:
            cls = "done"
        elif key == last and not run.done:
            cls = "cur"
        elif key in seen:
            cls = "done"
        else:
            cls = ""
        pills.append(f'<span class="ag-pill {cls}">{label}</span>')
    return f'<div class="ag-flow">{"".join(pills)}</div>'


def _kpis(result: dict) -> str:
    econ = result.get("econometric", {})
    items = []
    if "revenue_delta" in econ:
        items.append(f'<div>Δ выручка/день<b>{_signed(econ["revenue_delta"])}</b></div>')
    if "margin_delta" in econ:
        items.append(f'<div>Δ маржа/день<b>{_signed(econ["margin_delta"])}</b></div>')
    per = result.get("persona_simulation", {})
    if per:
        items.append(f'<div>гости: уйдут / переключатся<b>{per.get("leave_pct", 0)}% / {per.get("switch_pct", 0)}%</b></div>')
    return f'<div class="ag-kpi">{"".join(items)}</div>' if items else ""


def _step_html(step, is_new: bool) -> str:
    color, icon = KIND_STYLE.get(step.kind, KIND_STYLE["thought"])
    head = f'<div class="ag-h"><b>{_e(step.title)}</b><span class="ag-t">+{step.t:.1f} с</span></div>'
    body = ""
    if step.kind == "thinking":
        body = f'<div class="ag-think">{_e(step.text)}</div>'
    elif step.kind in ("question", "thought", "error") and step.text:
        body = f'<div class="ag-b">{_e(step.text)}</div>'
    elif step.kind == "tool_call":
        chips = "".join(f'<span class="ag-chip">{_e(k)} = {_e(v)}</span>' for k, v in step.data.get("args", {}).items())
        body = f'<div class="ag-chips">{chips}</div>'
    elif step.kind == "tool_result":
        res = step.data.get("result", {})
        if "error" in res:
            body = f'<div class="ag-b ag-neg">{_e(res["error"])}</div>'
        else:
            raw = json.dumps(res, ensure_ascii=False, indent=2)
            body = (f'<div class="ag-b">расчёт занял {step.data.get("ms", 0)} мс</div>{_kpis(res)}'
                    f'<details><summary>сырой ответ инструмента (JSON)</summary><pre>{html.escape(raw)}</pre></details>')
    cls = "ag-step new" if is_new else "ag-step"
    return f'<div class="{cls}" style="--c:{color}" data-ic="{icon}">{head}{body}</div>'


def timeline_html(run: AgentRun, show_thinking: bool = True) -> str:
    steps = [s for s in run.steps if s.kind != "answer" and (show_thinking or s.kind != "thinking")]
    last_idx = len(steps) - 1
    cards = "".join(_step_html(s, i == last_idx and not run.done) for i, s in enumerate(steps))
    live = ""
    if not run.done:
        live = '<div class="ag-live">агент работает</div>'
    return f'<div class="ag-tl">{cards}</div>{live}'


def stats_caption(run: AgentRun) -> str:
    mode = "LLM (Claude)" if run.mode == "llm" else "правила, без LLM"
    tok = f" · токены {run.tokens_in:,} → {run.tokens_out:,}" if run.mode == "llm" else ""
    return f"⏱ {run.elapsed:.1f} с · 🔧 вызовов инструмента: {run.tool_calls} · режим: {mode}{tok}"


def render_result_panel(result: dict) -> None:
    """Правая колонка: что агент увидел в результате инструмента."""
    econ = result.get("econometric", {})
    per = result.get("persona_simulation", {})
    sc = result.get("scenario", {})
    st.markdown("##### 📈 Что агент увидел")
    st.caption(f"Сценарий: {sc.get('type', '')} · {sc.get('sku_name') or sc.get('combo_name') or ''}")
    c1, c2 = st.columns(2)
    if "revenue_delta" in econ:
        c1.metric("Δ Выручка/день", f"{econ['revenue_delta']:,.0f} ₸", f"{econ.get('revenue_delta_pct', '')}%" if "revenue_delta_pct" in econ else None)
    if "margin_delta" in econ:
        c2.metric("Δ Маржа/день", f"{econ['margin_delta']:,.0f} ₸", f"{econ.get('margin_delta_pct', '')}%" if "margin_delta_pct" in econ else None)

    movers = result.get("per_sku_top_movers") or []
    if movers:
        names = [m["name"] for m in movers]
        vals = [m["revenue_delta"] for m in movers]
        fig = go.Figure(go.Bar(x=vals, y=names, orientation="h",
                               marker_color=["#10b981" if v >= 0 else "#ef4444" for v in vals],
                               text=[f"{v:+,.0f}" for v in vals], textposition="outside", cliponaxis=False))
        pad = max(abs(v) for v in vals) * 0.3 or 1
        fig.update_xaxes(range=[min(0, min(vals)) - pad, max(0, max(vals)) + pad])
        fig.update_layout(title="Куда движутся деньги (Δ выручки/день, ₸)", height=260,
                          margin=dict(l=0, r=30, t=40, b=0), yaxis=dict(autorange="reversed"), xaxis=dict(zeroline=True))
        st.plotly_chart(fig, use_container_width=True, key=f"mv_{id(result)}")

    if per:
        fig = go.Figure(go.Pie(labels=["Примут", "Переключатся", "Уйдут"],
                               values=[per.get("accept_pct", 0), per.get("switch_pct", 0), per.get("leave_pct", 0)],
                               hole=.55, marker=dict(colors=["#10b981", "#f59e0b", "#ef4444"]), sort=False,
                               textinfo="text",
                               text=[f"{v}%" if v else "" for v in (per.get("accept_pct", 0), per.get("switch_pct", 0), per.get("leave_pct", 0))]))
        fig.update_layout(title="Реакция 15 AI-персон гостей", height=240, margin=dict(l=0, r=0, t=40, b=0))
        st.plotly_chart(fig, use_container_width=True, key=f"pr_{id(result)}")
        if per.get("sample_objections"):
            with st.expander("Что говорят персоны"):
                for o in per["sample_objections"]:
                    st.write(f"- {o}")