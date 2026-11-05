# python 3.10+, agent loop for P03 Menu Simulator with a full step trace (question -> thinking -> tool -> result -> answer)
"""
Один агент с инструментами, у которого каждый шаг записывается в трассу (Step), чтобы сайт мог
показать, как он думает и что делает.

Два режима:
  llm    -- ANTHROPIC_API_KEY есть: Claude сам выбирает инструмент (simulate_price_change / simulate_removal /
            simulate_combo), видит результат и объясняет его. Если доступно, записываются и блоки размышлений.
  rules  -- ключа нет: прозрачный планировщик на правилах делает те же шаги (разбор вопроса -> инструмент ->
            ответ по шаблону). Режим честно помечается в трассе, это не LLM.

Расчёты в обоих режимах делает один и тот же код (simulator.py -> elasticity.py); агент ничего не придумывает
про деньги, он только выбирает инструмент и пересказывает его результат.
"""
import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import pandas as pd

from elasticity import load_data
from simulator import TOOLS, TOOL_IMPL

MODEL = os.environ.get("AGENT_MODEL", "claude-sonnet-4-5")
MAX_TURNS = 6
STEP_PAUSE = float(os.environ.get("AGENT_STEP_PAUSE", "0.45"))   # секунд между шагами в режиме правил
DATA_DIR = Path(__file__).parent / "data"

EXAMPLES = [
    "Что будет, если поднять цену на {sku} на 10%?",
    "Что если убрать {sku} из меню?",
    "Что даст комбо {combo}?",
]


@dataclass
class Step:
    kind: str            # question | thinking | thought | tool_call | tool_result | answer | error
    title: str
    text: str = ""
    data: dict = field(default_factory=dict)
    t: float = 0.0       # секунд от начала запроса


@dataclass
class AgentRun:
    question: str
    mode: str = "llm"    # llm | rules
    steps: list = field(default_factory=list)
    answer: str = ""
    result: Optional[dict] = None   # последний успешный результат инструмента
    elapsed: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    done: bool = False

    @property
    def tool_calls(self) -> int:
        return sum(1 for s in self.steps if s.kind == "tool_call")


class _Tracer:
    def __init__(self, run: AgentRun, on_step: Optional[Callable[[AgentRun], None]]):
        self.run, self.on_step, self.t0 = run, on_step, time.time()

    def add(self, kind: str, title: str, text: str = "", data: Optional[dict] = None) -> Step:
        if self.run.mode == "rules" and len(self.run.steps) > 0:
            time.sleep(STEP_PAUSE)   # режим правил мгновенный; пауза только ради читаемости ленты на сайте
        step = Step(kind, title, text, data or {}, round(time.time() - self.t0, 2))
        self.run.steps.append(step)
        self.run.elapsed = step.t
        if self.on_step:
            self.on_step(self.run)
        return step


# ----------------------------------------------------------------------------- public API
def run_agent(question: str, on_step: Optional[Callable[[AgentRun], None]] = None,
              use_thinking: bool = True, client=None) -> AgentRun:
    """Запускает агента. on_step(run) вызывается после каждого шага (для живой отрисовки).
    client -- готовый клиент Anthropic (для тестов); иначе создаётся из ANTHROPIC_API_KEY."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    run = AgentRun(question=question, mode="llm" if (client or api_key) else "rules")
    tr = _Tracer(run, on_step)
    tr.add("question", "Вопрос", question)
    menu, _ = load_data()
    try:
        if run.mode == "llm":
            if client is None:
                import anthropic
                client = anthropic.Anthropic(api_key=api_key)
            _run_llm(run, tr, client, use_thinking, menu)
        else:
            _run_rules(run, tr, menu)
    except Exception as e:  # агент не должен ронять сайт
        tr.add("error", "Ошибка агента", f"{type(e).__name__}: {e}")
        run.answer = run.answer or f"Не удалось завершить запрос: {type(e).__name__}: {e}"
    run.done = True
    run.elapsed = round(time.time() - tr.t0, 2)
    if on_step:
        on_step(run)
    return run


# ----------------------------------------------------------------------------- LLM mode
def _system_prompt(menu: pd.DataFrame) -> str:
    combos = pd.read_csv(DATA_DIR / "combos.csv")[["combo_id", "name"]].to_string(index=False)
    menu_ctx = menu[["sku_id", "name", "category", "price"]].to_string(index=False)
    return (
        "You are a restaurant menu what-if analyst for a fast-food chain. You have tools to simulate price "
        "changes, SKU removal and combo launches. Always call a tool for what-if questions, never guess numbers. "
        "After the tool result, answer in Russian in plain business language: revenue/margin impact, "
        "cannibalization (where demand moves), guest reaction, and one sentence on how reliable this is "
        "(it is a model estimate, not a forecast).\n\n"
        f"Menu:\n{menu_ctx}\n\nCombos:\n{combos}\n"
    )


def _run_llm(run: AgentRun, tr: _Tracer, client, use_thinking: bool, menu: pd.DataFrame) -> None:
    system = _system_prompt(menu)
    messages = [{"role": "user", "content": run.question}]
    thinking_on = use_thinking
    for _ in range(MAX_TURNS):
        kwargs = dict(model=MODEL, max_tokens=4096 if thinking_on else 1500, system=system,
                      tools=TOOLS, messages=messages)
        if thinking_on:
            kwargs["thinking"] = {"type": "enabled", "budget_tokens": 1024}
        try:
            resp = client.messages.create(**kwargs)
        except Exception as e:
            if thinking_on and not run.tool_calls:   # модель/ключ без размышлений: пробуем без них
                thinking_on = False
                tr.add("error", "Размышления модели недоступны, продолжаю без них", str(e)[:160])
                continue
            raise
        usage = getattr(resp, "usage", None)
        run.tokens_in += getattr(usage, "input_tokens", 0) or 0
        run.tokens_out += getattr(usage, "output_tokens", 0) or 0

        tool_results, final_text = [], []
        calling = resp.stop_reason == "tool_use"
        for b in resp.content:
            if b.type == "thinking":
                tr.add("thinking", "Размышляет", b.thinking)
            elif b.type == "redacted_thinking":
                tr.add("thinking", "Размышляет", "[часть размышлений скрыта моделью]")
            elif b.type == "text" and b.text.strip():
                if calling:
                    tr.add("thought", "Решает, что делать", b.text.strip())
                else:
                    final_text.append(b.text)
            elif b.type == "tool_use":
                tr.add("tool_call", f"Вызывает инструмент {b.name}", data={"name": b.name, "args": dict(b.input)})
                t0 = time.time()
                try:
                    out = TOOL_IMPL[b.name](b.input)
                except Exception as e:
                    out = {"error": f"{type(e).__name__}: {e}"}
                ms = round((time.time() - t0) * 1000)
                if "error" not in out:
                    run.result = out
                tr.add("tool_result", f"Получил результат {b.name}", data={"name": b.name, "result": out, "ms": ms})
                tool_results.append({"type": "tool_result", "tool_use_id": b.id,
                                     "content": json.dumps(out, ensure_ascii=False)})
        if not calling:
            run.answer = "".join(final_text).strip()
            tr.add("answer", "Формулирует итоговый ответ", data={"chars": len(run.answer)})
            return
        messages.append({"role": "assistant", "content": resp.content})
        messages.append({"role": "user", "content": tool_results})
    raise RuntimeError(f"агент не завершил работу за {MAX_TURNS} шагов")


# ----------------------------------------------------------------------------- rules mode
_NEG = re.compile(r"(снизи|уменьш|скидк|дешевле|удешев|минус|[-−–]\s*\d+\s*%)", re.I)
_REMOVE = re.compile(r"(убрат|удал|вывест|исключ|снять с меню|remove)", re.I)
_PRICE = re.compile(r"(цен|поднят|повыс|подорож|снизи|удешев|price)", re.I)


def _run_rules(run: AgentRun, tr: _Tracer, menu: pd.DataFrame) -> None:
    q = run.question
    ql = q.lower()
    combos = pd.read_csv(DATA_DIR / "combos.csv")
    tr.add("thought", "Режим без LLM (ключа нет)",
           "ANTHROPIC_API_KEY не задан, поэтому работает планировщик на правилах: ищу в вопросе тип изменения, "
           "позицию меню и процент. Расчёт тот же, что и в режиме LLM.")

    combo = next((r for _, r in combos.iterrows()
                  if str(r["name"]).lower() in ql or str(r["combo_id"]).lower() in ql), None)
    sku_hits = [r for _, r in menu.iterrows() if str(r["name"]).lower() in ql or str(r["sku_id"]).lower() in ql]
    sku = max(sku_hits, key=lambda r: len(str(r["name"]))) if sku_hits else None
    pct_m = re.search(r"(\d+(?:[.,]\d+)?)\s*%", q)
    pct = float(pct_m.group(1).replace(",", ".")) / 100 if pct_m else None

    if combo is not None and ("комбо" in ql or sku is None):
        kind = "combo"
    elif "комбо" in ql:
        combo, kind = combos.iloc[0], "combo"
    elif _REMOVE.search(q):
        kind = "removal"
    elif _PRICE.search(q) or pct is not None:
        kind = "price"
    else:
        kind = None

    if kind is None:
        tr.add("error", "Не понял, что симулировать",
               "Нужны тип изменения (цена, удаление, комбо) и название позиции из меню.")
        ex = EXAMPLES[0].format(sku=menu.iloc[0]["name"])
        run.answer = f"Я не понял вопрос. Попробуй так: «{ex}»"
        tr.add("answer", "Формулирует итоговый ответ", data={"chars": len(run.answer)})
        return

    notes = []
    if kind == "combo":
        tool, args = "simulate_combo", {"combo_id": combo["combo_id"]}
        plan = f"Тип: запуск комбо · комбо: «{combo['name']}» ({combo['combo_id']})"
    else:
        if sku is None:
            sku = menu.iloc[0]
            notes.append(f"позицию в вопросе не нашёл, беру первую в меню: «{sku['name']}»")
        if kind == "removal":
            tool, args = "simulate_removal", {"sku_id": sku["sku_id"]}
            plan = f"Тип: удаление позиции · «{sku['name']}» ({sku['sku_id']})"
        else:
            if pct is None:
                pct = 0.10
                notes.append("процент не указан, беру +10%")
            delta = -pct if _NEG.search(q) else pct
            tool, args = "simulate_price_change", {"sku_id": sku["sku_id"], "price_delta_pct": round(delta, 4)}
            plan = f"Тип: изменение цены · «{sku['name']}» ({sku['sku_id']}) · {delta * 100:+.0f}%"
    tr.add("thought", "Разобрал вопрос", plan + ("\nДопущения: " + "; ".join(notes) if notes else ""))

    tr.add("tool_call", f"Вызывает инструмент {tool}", data={"name": tool, "args": args})
    t0 = time.time()
    out = TOOL_IMPL[tool](args)
    ms = round((time.time() - t0) * 1000)
    if "error" not in out:
        run.result = out
    tr.add("tool_result", f"Получил результат {tool}", data={"name": tool, "result": out, "ms": ms})

    run.answer = compose_answer(out, notes)
    tr.add("answer", "Формулирует итоговый ответ", data={"chars": len(run.answer)})


def compose_answer(res: dict, notes: Optional[list] = None) -> str:
    """Шаблонный пересказ результата (режим без LLM)."""
    if "error" in res:
        return f"Инструмент вернул ошибку: {res['error']}"
    sc, econ, per = res.get("scenario", {}), res.get("econometric", {}), res.get("persona_simulation", {})
    kind = sc.get("type")
    if kind == "price_change":
        head = f"**Цена «{sc.get('sku_name')}» {sc.get('price_delta_pct', 0) * 100:+.0f}%**"
    elif kind == "remove_sku":
        head = f"**Удаление «{sc.get('sku_name')}» из меню**"
    else:
        head = f"**Запуск комбо «{sc.get('combo_name')}»**"

    rd, md = econ.get("revenue_delta", 0), econ.get("margin_delta", 0)
    rpct = econ.get("revenue_delta_pct")
    mpct = econ.get("margin_delta_pct")
    if rpct is None and econ.get("baseline_revenue_items_separately"):
        rpct = round(rd / econ["baseline_revenue_items_separately"] * 100, 2)
    if mpct is None and econ.get("baseline_margin_items_separately"):
        mpct = round(md / econ["baseline_margin_items_separately"] * 100, 2)
    lines = [head, "",
             f"- Выручка в день: **{rd:+,.0f} ₸**" + (f" ({rpct:+.2f}%)" if rpct is not None else ""),
             f"- Маржа в день: **{md:+,.0f} ₸**" + (f" ({mpct:+.2f}%)" if mpct is not None else "")]
    movers = res.get("per_sku_top_movers") or []
    own = next((m for m in movers if m["sku_id"] == sc.get("sku_id")), None)
    if own:
        lines.append(f"- Спрос на саму позицию: **{own['unit_delta_pct']:+.1f}%**")
    gain = [m for m in movers if m["sku_id"] != sc.get("sku_id") and m["revenue_delta"] > 0]
    if gain:
        g = max(gain, key=lambda m: m["revenue_delta"])
        lines.append(f"- Каннибализация: спрос больше всего перетекает в «{g['name']}» ({g['revenue_delta']:+,.0f} ₸)")
    if per:
        lines.append(f"- AI-персоны: примут {per.get('accept_pct', 0)}%, переключатся {per.get('switch_pct', 0)}%, "
                     f"уйдут {per.get('leave_pct', 0)}%")
    verdict = ("выгодно и по выручке, и по марже" if rd > 0 and md > 0 else
               "теряем и выручку, и маржу" if rd < 0 and md < 0 else
               "выручка и маржа двигаются в разные стороны, решает приоритет")
    lines += ["", f"Вывод: {verdict}. Это оценка модели на допущениях (эластичность по категориям, "
                  f"калибровка по одному дню), а не прогноз; проверять A/B-тестом."]
    if notes:
        lines += ["", "_Допущения агента: " + "; ".join(notes) + "._"]
    return "\n".join(lines)