import hashlib
import importlib
import json
import os
import shutil
import tempfile
import unittest

TEST_DATA_DIR = tempfile.mkdtemp()
os.environ["DATA_DIR"] = TEST_DATA_DIR
os.environ["ADMIN_SECRET"] = "test-secret"

import server  # noqa: E402

server = importlib.reload(server)


class _FakeAI:
    def generate_response(self, prompt, wallet=None, model_key=None, session_id=None):
        return {
            "response": "stub-response",
            "status": "ok",
            "provider": "openai",
            "model": "gpt-4o",
        }

    def generate_quantum_key(self):
        return "fake-key"


class AIInteractionTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(TEST_DATA_DIR, ignore_errors=True)

    def setUp(self):
        shutil.rmtree(TEST_DATA_DIR, ignore_errors=True)
        os.makedirs(TEST_DATA_DIR, exist_ok=True)
        server.ai_agent = _FakeAI()
        self.client = server.app.test_client()
        server.save_ai_credits({"THRabc": 5})

    def test_record_ai_interaction_hashes_prompt_and_output(self):
        prompt = "hello"
        output = "world"
        server.record_ai_interaction(
            session_id="s1",
            user_wallet="THRabc",
            provider="openai",
            model="gpt-4o",
            prompt=prompt,
            output=output,
            tokens_input=1,
            tokens_output=1,
            cost_usd=0.1,
            latency_ms=123,
            ai_credits_spent=1.0,
        )

        interactions = server.load_ai_interactions()
        self.assertEqual(len(interactions), 1)
        entry = interactions[0]
        self.assertEqual(entry["input_hash"], hashlib.sha256(prompt.encode("utf-8")).hexdigest())
        self.assertEqual(entry["output_hash"], hashlib.sha256(output.encode("utf-8")).hexdigest())
        self.assertNotIn("prompt", entry)
        self.assertNotIn("output", entry)

    def test_feedback_endpoint_updates_entry(self):
        created = server.record_ai_interaction(
            session_id="s2",
            user_wallet="THRabc",
            provider="openai",
            model="gpt-4o",
            prompt="hello",
            output="world",
            tokens_input=1,
            tokens_output=1,
            cost_usd=0.1,
            latency_ms=50,
            ai_credits_spent=1.0,
        )

        resp = self.client.post(
            f"{server.API_BASE_PREFIX}/ai/interactions/{created['id']}/feedback",
            json={"score": 2, "tags": ["helpful", "quick"]},
        )
        self.assertEqual(resp.status_code, 200)

        interactions = server.load_ai_interactions()
        entry = interactions[0]
        self.assertEqual(entry["feedback"].get("score"), 2)
        self.assertEqual(entry["feedback"].get("tags"), ["helpful", "quick"])

    def test_admin_metrics_and_listing(self):
        for idx in range(3):
            server.record_ai_interaction(
                session_id=f"s{idx}",
                user_wallet=f"THR{idx}",
                provider="openai" if idx % 2 == 0 else "anthropic",
                model="gpt-4o" if idx % 2 == 0 else "claude-3",
                prompt=f"p{idx}",
                output=f"o{idx}",
                tokens_input=1,
                tokens_output=1,
                cost_usd=0.0,
                latency_ms=10,
                ai_credits_spent=1.0,
            )

        resp_forbidden = self.client.get(f"{server.API_BASE_PREFIX}/ai/interactions")
        self.assertEqual(resp_forbidden.status_code, 403)

        resp = self.client.get(
            f"{server.API_BASE_PREFIX}/ai/interactions",
            query_string={"secret": os.environ["ADMIN_SECRET"], "provider": "openai"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["total"], 2)

        metrics = self.client.get(
            f"{server.API_BASE_PREFIX}/ai/metrics/summary",
            query_string={"secret": os.environ["ADMIN_SECRET"]},
        )
        self.assertEqual(metrics.status_code, 200)
        summary = metrics.get_json()
        self.assertIn("by_model", summary)
        self.assertIn("openai:gpt-4o", summary["by_model"])

        public_metrics = self.client.get("/api/ai/metrics")
        self.assertEqual(public_metrics.status_code, 200)
        payload = public_metrics.get_json()
        self.assertIn("models", payload)
        self.assertIn("openai:gpt-4o", payload["models"])

    def test_chat_endpoint_records_interaction(self):
        resp = self.client.post(
            "/api/chat",
            json={"message": "Hi", "wallet": "THRabc", "session_id": "sess-1"},
        )
        self.assertEqual(resp.status_code, 200, resp.get_data(as_text=True))

        interactions = server.load_ai_interactions()
        self.assertEqual(len(interactions), 1)
        entry = interactions[0]
        self.assertEqual(entry["user_wallet"], "THRabc")
        self.assertEqual(entry["provider"], "openai")


if __name__ == "__main__":
    unittest.main()
