import json
import unittest
from unittest.mock import patch

from rag import answer_question, semantic_retrieve


class RagTests(unittest.TestCase):
    def test_restricted_text_is_excluded_from_both_model_requests(self):
        payloads = []

        def model_response(endpoint, payload):
            payloads.append(payload)
            if endpoint == "embed":
                return {"embeddings": [[1.0, 0.0] for _ in payload["input"]]}
            return {"done": True, "message": {"content": "I do not have enough information."}}

        with patch("rag.request_ollama", side_effect=model_response):
            result = answer_question("administrator emergency recovery code", "employee")

        self.assertEqual(len(payloads), 2)
        for payload in payloads:
            self.assertNotIn("DEMO-RECOVERY-47", json.dumps(payload))
            self.assertNotIn("recovery-procedure", json.dumps(payload))
        self.assertTrue(result["chunks"])
        self.assertTrue(all("employee" in chunk["roles"] for chunk in result["chunks"]))

    def test_semantic_ranking_passes_allowed_sources_to_chat(self):
        def model_response(endpoint, payload):
            if endpoint == "embed":
                vectors = [[1.0, 0.0]]
                for text in payload["input"][1:]:
                    vectors.append([1.0, 0.0] if "DEMO-RECOVERY-47" in text else [0.0, 1.0])
                return {"embeddings": vectors}
            context = json.loads(payload["messages"][1]["content"])
            self.assertEqual(context["sources"][0]["id"], "recovery-procedure:1")
            return {"done": True, "message": {"content": "DEMO-RECOVERY-47 [recovery-procedure:1]"}}

        with patch("rag.request_ollama", side_effect=model_response):
            result = answer_question("recovery code", "admin")
        self.assertIn("DEMO-RECOVERY-47", result["answer"])
        self.assertEqual(result["chunks"][0]["source"], "corpus/recovery-procedure.md")

    def test_unknown_role_rejected_before_model_request(self):
        with patch("rag.request_ollama") as request:
            with self.assertRaises(ValueError):
                answer_question("recovery code", "guest")
            request.assert_not_called()

    def test_no_permitted_documents_skips_both_models(self):
        with patch("retrieve.load_chunks", return_value=[]), patch("rag.request_ollama") as request:
            self.assertEqual(answer_question("VPN", "employee")["chunks"], [])
            request.assert_not_called()

    def test_malformed_embeddings_stop_before_generation(self):
        chunks = [{"id": "faq:1", "title": "FAQ", "text": "VPN", "roles": ["employee"]}]
        malformed = [
            [], [[1.0, 0.0]], [[1.0, 0.0], [0.0]], [[0.0], [1.0]],
            [[1.0], [float("nan")]],
        ]
        for vectors in malformed:
            with self.subTest(vectors=vectors):
                with patch("rag.authorized_chunks", return_value=chunks), patch(
                    "rag.request_ollama", return_value={"embeddings": vectors}
                ) as request:
                    with self.assertRaises(RuntimeError):
                        semantic_retrieve("VPN", "employee")
                    self.assertEqual(request.call_count, 1)

    def test_model_failure_returns_no_answer(self):
        with patch("rag.request_ollama", side_effect=RuntimeError("Unavailable")):
            with self.assertRaises(RuntimeError):
                answer_question("VPN", "employee")

    def test_incomplete_generated_answer_is_rejected(self):
        responses = [
            {}, {"done": False, "message": {"content": "partial"}},
            {"done": True, "done_reason": "length", "message": {"content": "cut off"}},
        ]
        for response in responses:
            with self.subTest(response=response):
                with patch("rag.semantic_retrieve", return_value=[{"id": "faq:1", "text": "VPN"}]), patch(
                    "rag.request_ollama", return_value=response
                ):
                    with self.assertRaises(RuntimeError):
                        answer_question("VPN", "employee")
