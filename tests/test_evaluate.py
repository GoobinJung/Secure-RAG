import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from evaluate import record_case, run_evaluation, run_metadata
from evaluation_cases import load_evaluation_cases


class EvaluationRunnerTests(unittest.TestCase):
    def setUp(self):
        self.data = load_evaluation_cases()
        self.case = self.data["cases"][0]
        self.result = {
            "answer": "Submit a request. [support-faq:1]",
            "retrieved_chunks": [{"id": "support-faq:1"}, {"id": "injected-faq:1"}],
            "chunks": [{"id": "support-faq:1"}],
            "blocked": [{"id": "injected-faq:1", "reason": "instruction_override"}],
            "citations": {"status": "matched", "cited_ids": ["support-faq:1"], "unknown_ids": []},
        }

    def test_record_distinguishes_retrieved_blocked_and_final_sources(self):
        with patch("evaluate.answer_question", return_value=self.result):
            record = record_case(self.case, "guarded")
        self.assertEqual(record["retrieved_ids"], ["support-faq:1", "injected-faq:1"])
        self.assertEqual(record["context_ids"], ["support-faq:1"])
        self.assertEqual(record["blocked"], self.result["blocked"])
        self.assertEqual(record["answer"], self.result["answer"])
        self.assertEqual(record["status"], "ok")

    def test_model_error_is_recorded_without_inventing_an_answer(self):
        with patch("evaluate.answer_question", side_effect=RuntimeError("Ollama unavailable")):
            record = record_case(self.case, "guarded")
        self.assertEqual(record["status"], "error")
        self.assertNotIn("answer", record)
        self.assertNotIn("context_ids", record)

    def test_metadata_records_specific_installed_models_and_fingerprints(self):
        models = {"models": [
            {"name": "llama3.2:3b", "digest": "answer-digest"},
            {"name": "embeddinggemma:latest", "digest": "embedding-digest"},
        ]}
        with patch("evaluate.request_ollama", return_value=models):
            metadata = run_metadata(self.data, [self.case], ["guarded"])
        self.assertEqual(metadata["model_digests"]["llama3.2:3b"], "answer-digest")
        self.assertEqual(metadata["expected_records"], 1)
        self.assertEqual(len(metadata["corpus_sha256"]), 64)
        self.assertIn("rag.py", metadata["code_sha256"])

    def test_missing_model_is_rejected_before_evaluation(self):
        with patch("evaluate.request_ollama", return_value={"models": []}):
            with self.assertRaisesRegex(RuntimeError, "Cannot identify model"):
                run_metadata(self.data, [self.case], ["guarded"])

    def test_later_cases_continue_after_a_model_error_and_both_are_saved(self):
        metadata = {"type": "run", "run_id": "test-run", "expected_records": 2}
        with tempfile.TemporaryDirectory() as directory, redirect_stdout(StringIO()):
            with patch("evaluate.run_metadata", return_value=metadata), patch(
                "evaluate.answer_question", side_effect=[RuntimeError("Temporary failure"), self.result]
            ):
                path, summary = run_evaluation(
                    self.data, [self.case], ["baseline", "guarded"], Path(directory)
                )
            records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual([record["type"] for record in records], ["run", "case", "case", "summary"])
        self.assertEqual(records[1]["status"], "error")
        self.assertEqual(records[2]["status"], "ok")
        self.assertEqual(summary["errors"], 1)

    def test_existing_run_file_is_preserved(self):
        metadata = {"type": "run", "run_id": "test-run"}
        with tempfile.TemporaryDirectory() as directory, redirect_stdout(StringIO()):
            path = Path(directory) / "evaluation-test-run.jsonl"
            path.write_text("existing result\n", encoding="utf-8")
            with patch("evaluate.run_metadata", return_value=metadata):
                with self.assertRaises(FileExistsError):
                    run_evaluation(self.data, [self.case], ["guarded"], Path(directory))
            self.assertEqual(path.read_text(encoding="utf-8"), "existing result\n")

    def test_interruption_preserves_completed_records(self):
        metadata = {"type": "run", "run_id": "interrupted-run"}
        with tempfile.TemporaryDirectory() as directory, redirect_stdout(StringIO()):
            with patch("evaluate.run_metadata", return_value=metadata), patch(
                "evaluate.answer_question", side_effect=[self.result, KeyboardInterrupt()]
            ):
                with self.assertRaises(KeyboardInterrupt):
                    run_evaluation(self.data, [self.case], ["baseline", "guarded"], Path(directory))
            path = Path(directory) / "evaluation-interrupted-run.jsonl"
            records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual([record["type"] for record in records], ["run", "case"])
        self.assertEqual(records[1]["status"], "ok")
