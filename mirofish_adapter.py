# python 3.10+, adapter: Menu Simulator scenario -> MiroFish multi-agent simulation -> markdown report
"""
Экспериментальный слой. Основная модель (elasticity.py) считает деньги; MiroFish даёт
качественное "второе мнение": агенты-гости обсуждают изменение меню в симулированной соцсети,
ReportAgent пишет отчёт. Результат НЕ влияет на выручку/маржу и не является доказательством
поведения реальных гостей.

Конвейер (эндпоинты проверены по исходникам MiroFish backend/app/api/*.py):
  1. POST /api/graph/ontology/generate   multipart: files + simulation_requirement  -> project_id
  2. POST /api/graph/build               {project_id}                                -> task_id (poll /api/graph/task/<id>)
  3. POST /api/simulation/create         {project_id, enable_twitter, enable_reddit} -> simulation_id
  4. POST /api/simulation/prepare        {simulation_id}                             -> task_id (poll /prepare/status)
  5. POST /api/simulation/start          {simulation_id, platform, max_rounds}       (poll /<id>/run-status)
  6. POST /api/report/generate           {simulation_id}                             (poll /generate/status) -> report_id
  7. GET  /api/report/<report_id>        -> markdown_content

Требования: запущенный MiroFish (см. README, раздел MiroFish), в его .env -- LLM_API_KEY и ZEP_API_KEY.
"""
import os
import time
import requests

MIROFISH_URL = os.environ.get("MIROFISH_URL", "http://localhost:5001").rstrip("/")
# MiroFish принимает только 'en' или 'zh' в Accept-Language (utils/locale.py), русского нет.
HEADERS = {"Accept-Language": "en"}


class MiroFishError(Exception):
    def __init__(self, stage: str, message: str):
        super().__init__(f"[{stage}] {message}")
        self.stage, self.message = stage, message


def is_available(timeout: float = 3.0) -> tuple[bool, str]:
    """Быстрая проверка, что бэкенд MiroFish отвечает."""
    try:
        r = requests.get(f"{MIROFISH_URL}/api/graph/project/list", headers=HEADERS, timeout=timeout)
        return (r.status_code < 500), f"HTTP {r.status_code}"
    except requests.RequestException as e:
        return False, type(e).__name__


def _call(stage: str, method: str, path: str, **kw) -> dict:
    try:
        r = requests.request(method, f"{MIROFISH_URL}{path}", headers=HEADERS, timeout=kw.pop("timeout", 60), **kw)
        body = r.json()
    except requests.RequestException as e:
        raise MiroFishError(stage, f"нет связи с MiroFish ({MIROFISH_URL}): {e}")
    except ValueError:
        raise MiroFishError(stage, f"ответ не JSON (HTTP {r.status_code}): {r.text[:200]}")
    if not body.get("success", False):
        raise MiroFishError(stage, str(body.get("error") or body)[:400])
    return body.get("data") or {}


def _poll(stage, fn, done, failed, timeout_s, interval=4.0, progress_cb=None):
    """Опрашивает fn() до done(data) или failed(data); бросает MiroFishError по таймауту."""
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        data = fn()
        if progress_cb:
            progress_cb(stage, data)
        if failed(data):
            raise MiroFishError(stage, str(data.get("error") or data.get("message") or data)[:400])
        if done(data):
            return data
        time.sleep(interval)
    raise MiroFishError(stage, f"таймаут {timeout_s} с")


def build_seed(result: dict) -> str:
    """Текст-«семя» для MiroFish: из него строится граф сущностей (рестораны, сегменты гостей, конкуренты).
    Описываем действующих лиц явно, иначе онтология получится пустой."""
    from personas import PERSONAS  # локальный импорт: адаптер можно импортировать без остального проекта
    sc = result.get("scenario", {})
    econ = result.get("econometric", {})
    kind = sc.get("type")
    if kind == "price_change":
        change = f"the price of '{sc.get('sku_name')}' changes by {sc.get('price_delta_pct', 0) * 100:+.0f}%"
    elif kind == "remove_sku":
        change = f"the item '{sc.get('sku_name')}' is REMOVED from the menu"
    else:
        change = f"a new combo is launched: {sc.get('combo_name') or sc.get('combo_id')}"

    cast = "\n".join(
        f"- {p['name']} (price sensitivity {p['budget_sensitivity']}, loyalty {p['loyalty']}, "
        f"likes: {', '.join(p['prefers'])})" for p in PERSONAS
    )
    return f"""# Menu change at a fast-food restaurant chain in Almaty, Kazakhstan

## The restaurant
I'M Kazakhstan is a fast-food restaurant chain with 16 locations in Almaty. It sells burgers, sides,
drinks, desserts, pizza and pasta. Its direct competitors are other fast-food chains and local cafes
in the same malls and streets. Many guests also order through delivery apps.

## The change under discussion
Next month {change}.

Economic baseline (estimated by an elasticity model, per day, one restaurant):
{', '.join(f'{k}={v}' for k, v in econ.items())}

## Guests (each is a separate person in the community who discusses the change online)
{cast}

## What we want to understand
How do these guests react in conversations with each other? Who accepts the change quietly, who
complains, who switches to a cheaper or similar item, who goes to a competitor, and why? Which
objections appear most often, and does the opinion of loyal regulars influence first-time visitors?
"""


def run_mirofish(result: dict, max_rounds: int = 8, progress_cb=None, stage_timeout_s: int = 900) -> dict:
    """Полный прогон. Возвращает {'ok': True, 'report_markdown', 'simulation_id', ...} или {'ok': False, 'stage', 'error'}."""
    t0 = time.time()
    try:
        seed = build_seed(result).encode("utf-8")

        d = _call("ontology", "POST", "/api/graph/ontology/generate", timeout=300,
                  files={"files": ("menu_change_seed.md", seed, "text/markdown")},
                  data={"simulation_requirement": "Predict how restaurant guests react to the menu change: "
                                                  "acceptance, complaints, switching to substitutes, leaving for competitors.",
                        "project_name": f"menu-whatif-{int(t0)}"})
        project_id = d["project_id"]

        d = _call("graph", "POST", "/api/graph/build", json={"project_id": project_id})
        task_id = d["task_id"]
        _poll("graph", lambda: _call("graph", "GET", f"/api/graph/task/{task_id}"),
              lambda x: x.get("status") == "completed", lambda x: x.get("status") == "failed",
              stage_timeout_s, progress_cb=progress_cb)

        d = _call("create", "POST", "/api/simulation/create",
                  json={"project_id": project_id, "enable_twitter": True, "enable_reddit": False})
        sim_id = d["simulation_id"]

        d = _call("prepare", "POST", "/api/simulation/prepare", json={"simulation_id": sim_id})
        if not d.get("already_prepared"):
            task_id = d["task_id"]
            _poll("prepare", lambda: _call("prepare", "POST", "/api/simulation/prepare/status", json={"task_id": task_id}),
                  lambda x: x.get("status") in ("completed", "ready") or x.get("already_prepared"),
                  lambda x: x.get("status") == "failed", stage_timeout_s, progress_cb=progress_cb)

        _call("start", "POST", "/api/simulation/start",
              json={"simulation_id": sim_id, "platform": "twitter", "max_rounds": int(max_rounds),
                    "enable_graph_memory_update": True})
        # 1) ждём, пока платформа отработала все раунды (simulation_end в actions.jsonl)
        _poll("simulation", lambda: _call("simulation", "GET", f"/api/simulation/{sim_id}/run-status"),
              lambda x: x.get("twitter_completed") or x.get("runner_status") in ("completed", "stopped"),
              lambda x: x.get("runner_status") == "failed", stage_timeout_s * 2, interval=6.0, progress_cb=progress_cb)
        # 2) скрипт после симуляции ждёт команд (режим интервью) и не выходит сам; без close-env
        #    MiroFish не публикует финальный статус и отказывается генерировать отчёт
        try:
            _call("close", "POST", "/api/simulation/close-env", json={"simulation_id": sim_id, "timeout": 30})
        except MiroFishError:
            pass  # окружение уже могло закрыться
        _poll("finalize", lambda: _call("finalize", "GET", f"/api/simulation/{sim_id}/run-status"),
              lambda x: x.get("runner_status") in ("completed", "stopped"),
              lambda x: x.get("runner_status") == "failed", 300, interval=5.0, progress_cb=progress_cb)

        d = _call("report", "POST", "/api/report/generate", json={"simulation_id": sim_id})
        report_id = d.get("report_id")
        task_id = d.get("task_id")
        if task_id:   # отчёт ещё генерируется; если уже был готов, task_id нет -- сразу забираем
            _poll("report", lambda: _call("report", "POST", "/api/report/generate/status", json={"task_id": task_id}),
                  lambda x: x.get("status") == "completed", lambda x: x.get("status") == "failed",
                  stage_timeout_s, progress_cb=progress_cb)
        if not report_id:
            raise MiroFishError("report", "MiroFish не вернул report_id")

        rep = _call("report", "GET", f"/api/report/{report_id}")
        return {"ok": True, "report_markdown": rep.get("markdown_content", ""), "report_id": report_id,
                "simulation_id": sim_id, "project_id": project_id, "rounds": int(max_rounds),
                "elapsed_s": round(time.time() - t0)}
    except MiroFishError as e:
        return {"ok": False, "stage": e.stage, "error": e.message, "elapsed_s": round(time.time() - t0)}
    except KeyError as e:
        return {"ok": False, "stage": "parse", "error": f"в ответе MiroFish нет поля {e}; API мог измениться",
                "elapsed_s": round(time.time() - t0)}


if __name__ == "__main__":
    ok, info = is_available()
    print("MiroFish доступен:", ok, info)
    if ok:
        from simulator import simulate_price_change
        res = run_mirofish(simulate_price_change("SKU001", 0.10), max_rounds=5,
                           progress_cb=lambda s, d: print(f"  {s}: {d.get('status') or d.get('runner_status')} {d.get('progress', d.get('progress_percent', ''))}"))
        print(res if not res["ok"] else res["report_markdown"][:2000])