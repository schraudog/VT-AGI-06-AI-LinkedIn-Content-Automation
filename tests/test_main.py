import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import main


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)
        self.request = {
            "brand": {"name": "FinEdge", "voice": "clear", "audience": "professionals"},
            "context": "Digital payments",
        }

    def test_multi_agent_response_and_inputs(self):
        results = [
            main.Ideas(ideas=["First", "Second", "Third"]),
            main.Draft(draft="A useful post", confidence=0.82),
            main.Hashtags(hashtags=["#Fintech", "#Payments"]),
        ]
        with patch("main.ask_agent", side_effect=results) as agent:
            response = self.client.post("/linkedin", json=self.request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {
            "ideas": ["First", "Second", "Third"], "draft": "A useful post",
            "confidence": 0.82, "hashtags": ["#Fintech", "#Payments"],
        })
        self.assertEqual(agent.call_args_list[1].args[1]["ideas"], results[0].ideas)
        self.assertEqual(agent.call_args_list[2].args[1]["draft"], results[1].draft)

    def test_invalid_input_and_missing_provider(self):
        self.assertEqual(self.client.post("/linkedin", json={}).status_code, 422)
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}):
            self.assertEqual(self.client.post("/linkedin", json=self.request).status_code, 503)

    def test_invalid_model_output_stops_generation(self):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def read(self, *args):
                return b'{"choices":[{"message":{"content":"{\\"ideas\\":[]}"}}]}'

        with patch.dict(os.environ, {"OPENAI_API_KEY": "test"}), patch("main.urlopen", return_value=Response()) as urlopen:
            self.assertEqual(self.client.post("/linkedin", json=self.request).status_code, 502)
            self.assertEqual(urlopen.call_args.args[0].get_header("Authorization"), "Bearer " + "test")

    def test_logging_and_validation(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"RUNS_DB_PATH": os.path.join(directory, "runs.db")}
        ):
            record = {"execution_id": "123", "final_text": "Post #Fintech",
                      "confidence": 0.8, "route": "review"}
            self.assertEqual(self.client.post("/runs", json=record).status_code, 201)
            self.assertEqual(self.client.post("/runs", json={**record, "confidence": 2}).status_code, 422)
            with sqlite3.connect(os.environ["RUNS_DB_PATH"]) as db:
                self.assertEqual(db.execute("SELECT execution_id, final_text, route FROM runs").fetchall(),
                                 [("123", "Post #Fintech", "review")])


if __name__ == "__main__":
    unittest.main()
