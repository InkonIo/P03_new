# python, проверка промо-модуля: факт по акции, прогноз по аналогам, окупаемость, агент и MiroFish seed.
# Запуск: python -m unittest discover -s tests -v   (из корня menu_simulator, нужны data/real_daily_revenue.csv и data/promo_calendar.xlsx)
import os, sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.pop("ANTHROPIC_API_KEY", None)
import promo_engine as pe
import agent_trace
import mirofish_adapter
import simulator
import report

agent_trace.STEP_PAUSE = 0


class PromoEngine(unittest.TestCase):
    def test_event_matching(self):
        self.assertEqual(pe.event_by_id("Как сработала акция Yandex −40% на Бифкурт")["id"], "yandex_aug04")
        self.assertEqual(pe.event_by_id("glovo бифкурт")["id"], "glovo_jul24")
        self.assertEqual(pe.event_by_id("i'm cup")["id"], "icup")
        self.assertIsNone(pe.event_by_id("акция wolt"))

    def test_history_numbers_consistent(self):
        h = pe.promo_history("yandex_aug04")
        e = h["econometric"]
        self.assertGreater(e["checks_per_day_after"], e["checks_per_day_before"])
        self.assertEqual(h["verdict"]["checks"], "up")
        self.assertEqual(pe.promo_history("icup")["verdict"]["checks"], "flat")
        self.assertIn("error", pe.promo_history("zzz"))

    def test_forecast_uses_same_channel_and_breakeven(self):
        f = pe.forecast_promo("Yandex", 40)
        self.assertEqual(f["analogs_n"], 2)
        self.assertEqual(f["econometric"]["restaurant_discount_pct"], 20.0)   # пополам
        self.assertAlmostEqual(f["econometric"]["breakeven_item_uplift_pct"], 44.4, places=1)
        g = pe.forecast_promo("Glovo", 30)
        self.assertEqual(g["scenario"]["funded_by"], "агрегатор")
        self.assertIsNone(g["econometric"]["breakeven_item_uplift_pct"])
        lo, hi = f["econometric"]["revenue_delta_range"]
        self.assertLessEqual(lo, f["econometric"]["revenue_delta"]); self.assertLessEqual(f["econometric"]["revenue_delta"], hi)
        self.assertIn("error", pe.forecast_promo("Телеграм", 30))

    def test_breakeven_table(self):
        b = pe.breakeven_table()
        self.assertGreater(len(b), 20)
        agg = b[b.restaurant_discount_pct <= 0.5]
        self.assertTrue(agg.pays_off.all())            # скидку платит агрегатор
        r = b[(b.platform == "Yandex") & (b["item"] == "Бифкурт (увел.)")].iloc[0]
        self.assertFalse(r.pays_off)                    # прогноз +25% < нужных +44%


class Integration(unittest.TestCase):
    def test_simulate_promo_has_personas_with_labels(self):
        r = simulator.simulate_promo("Wolt", 20, "", 7)
        self.assertEqual(r["persona_simulation"]["total_personas"], 15)
        self.assertEqual(len(r["persona_simulation"]["labels"]), 3)

    def test_agent_rules_mode_promo(self):
        run = agent_trace.run_agent("Как сработала акция Yandex −40% на Бифкурт и Чикенкурт?", use_thinking=False)
        self.assertEqual([s.data.get("name") for s in run.steps if s.kind == "tool_call"], ["promo_history"])
        self.assertIn("Гостей в день", run.answer)
        run = agent_trace.run_agent("Что если запустить скидку 30% на доставке в Glovo на 2 недели?", use_thinking=False)
        call = next(s for s in run.steps if s.kind == "tool_call")
        self.assertEqual(call.data["args"], {"channel": "Glovo", "guest_discount_pct": 30.0, "duration_days": 14})
        self.assertIn("агрегатор", run.answer)

    def test_agent_old_scenarios_still_route(self):
        run = agent_trace.run_agent("Что будет, если поднять цену на Биф Тейсти на 10%?", use_thinking=False)
        self.assertEqual(next(s for s in run.steps if s.kind == "tool_call").data["name"], "simulate_price_change")
        run = agent_trace.run_agent("что даст комбо Завтрак дуо", use_thinking=False)
        self.assertEqual(next(s for s in run.steps if s.kind == "tool_call").data["args"]["combo_id"], "COMBO02")

    def test_mirofish_seed_and_report(self):
        r = simulator.simulate_promo("Yandex", 40)
        seed = mirofish_adapter.build_seed(r)
        self.assertIn("40% discount", seed); self.assertIn("Yandex", seed)
        path = report.generate_report(r, "report_unittest_promo.md")
        try:
            txt = path.read_text(encoding="utf-8")
            self.assertIn("Аналоги", txt); self.assertIn("Оговорка", txt)
        finally:
            path.unlink()


if __name__ == "__main__":
    unittest.main()