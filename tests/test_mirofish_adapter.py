# python, проверка adapter-а на моке MiroFish API (настоящий MiroFish требует ключи LLM и Zep).
# Запуск: python -m unittest tests.test_mirofish_adapter -v   (из корня menu_simulator)
import json, sys, threading, unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import mirofish_adapter as mf

RESULT = {"scenario": {"type": "price_change", "sku_id": "SKU001", "sku_name": "Beef Tasty", "price_delta_pct": 0.1},
          "econometric": {"revenue_delta": 511, "margin_delta": 705}}

class Mock(BaseHTTPRequestHandler):
    calls, fail_graph, polls = [], False, {}
    def _j(self, data, ok=True):
        b = json.dumps({"success": ok, "data": data} if ok else {"success": False, "error": data}).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(b)
    def _seq(self, key, seq):
        n = Mock.polls.get(key, 0); Mock.polls[key] = n + 1; return seq[min(n, len(seq) - 1)]
    def do_GET(self):
        p = self.path; Mock.calls.append(("GET", p))
        if p.startswith("/api/graph/task/"):
            st = "failed" if Mock.fail_graph else self._seq("graph", ["processing", "completed"])
            return self._j({"status": st, "progress": 50, "error": "zep quota" if Mock.fail_graph else None})
        if p.endswith("/run-status"):
            return self._j({"runner_status": self._seq("run", ["running", "running", "completed"]), "progress_percent": 50})
        if p.startswith("/api/report/report_"):
            return self._j({"markdown_content": "# Report\nGuests complain about price."})
        if p == "/api/graph/project/list": return self._j([])
        self._j("not found", ok=False)
    def do_POST(self):
        p = self.path; Mock.calls.append(("POST", p))
        n = int(self.headers.get("Content-Length", 0)); body = self.rfile.read(n)
        if p == "/api/graph/ontology/generate":
            assert b"menu_change_seed.md" in body and b"Beef Tasty" in body, "seed не передан"
            return self._j({"project_id": "proj_1"})
        if p == "/api/graph/build": return self._j({"task_id": "t_graph"})
        if p == "/api/simulation/create": return self._j({"simulation_id": "sim_1"})
        if p == "/api/simulation/prepare": return self._j({"task_id": "t_prep", "status": "preparing", "already_prepared": False})
        if p == "/api/simulation/prepare/status": return self._j({"status": self._seq("prep", ["processing", "completed"])})
        if p == "/api/simulation/start":
            assert json.loads(body)["max_rounds"] == 5; return self._j({"runner_status": "running"})
        if p == "/api/report/generate": return self._j({"task_id": "t_rep", "report_id": "report_abc", "status": "generating"})
        if p == "/api/report/generate/status": return self._j({"status": self._seq("rep", ["processing", "completed"])})
        self._j("not found", ok=False)
    def log_message(self, *a): pass

class T(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = HTTPServer(("127.0.0.1", 0), Mock); cls.port = cls.srv.server_port
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        mf.time.sleep = lambda s: None
    @classmethod
    def tearDownClass(cls): cls.srv.shutdown()
    def setUp(self):
        mf.MIROFISH_URL = f"http://127.0.0.1:{self.port}"; Mock.calls.clear(); Mock.polls.clear(); Mock.fail_graph = False

    def test_full_pipeline_order_and_report(self):
        r = mf.run_mirofish(RESULT, max_rounds=5)
        self.assertTrue(r["ok"], r)
        self.assertIn("Guests complain", r["report_markdown"])
        paths = [p for _, p in Mock.calls]
        order = ["/api/graph/ontology/generate", "/api/graph/build", "/api/simulation/create", "/api/simulation/prepare",
                 "/api/simulation/start", "/api/report/generate", "/api/report/report_abc"]
        idx = [paths.index(o) for o in order]
        self.assertEqual(idx, sorted(idx))

    def test_graph_failure_reports_stage_and_reason(self):
        Mock.fail_graph = True
        r = mf.run_mirofish(RESULT, max_rounds=5)
        self.assertFalse(r["ok"]); self.assertEqual(r["stage"], "graph"); self.assertIn("zep quota", r["error"])
        self.assertNotIn("/api/simulation/create", [p for _, p in Mock.calls])  # дальше не идём

    def test_unreachable_server(self):
        mf.MIROFISH_URL = "http://127.0.0.1:9"
        r = mf.run_mirofish(RESULT, max_rounds=5)
        self.assertFalse(r["ok"]); self.assertEqual(r["stage"], "ontology")
        self.assertFalse(mf.is_available(1)[0])

    def test_availability_ok(self):
        self.assertTrue(mf.is_available()[0])

    def test_seed_contains_cast_and_scenario(self):
        s = mf.build_seed(RESULT)
        for needle in ("Beef Tasty", "+10%", "Budget Student", "Loyal Regular", "competitors"):
            self.assertIn(needle, s)

if __name__ == "__main__":
    unittest.main()
