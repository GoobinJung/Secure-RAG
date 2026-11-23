import copy
import unittest

from summarize_evaluation import fraction, summarize_records


class EvaluationMetricTests(unittest.TestCase):
    def setUp(self):
        self.metadata = {
            "run_id": "test", "answer_model": "llama3.2:3b",
            "selected_case_ids": ["attack-test"], "defense_modes": ["guarded"], "expected_records": 1,
            "source_labels": {"clean:1": "benign", "attack:1": "attack"},
            "attack_markers": {"attack:1": "DEMO-MARKER"},
        }
        self.record = {
            "case": {"id": "attack-test", "attack": {"source_id": "attack:1", "marker": "DEMO-MARKER"},
                     "reference_source_ids": ["clean:1"], "forbidden_source_ids": [], "forbidden_answer_text": []},
            "defense": "guarded", "status": "ok", "elapsed_seconds": 2.0,
            "retrieved_ids": ["clean:1", "attack:1"], "context_ids": ["clean:1"],
            "blocked": [{"id": "attack:1"}], "answer": "Normal answer [clean:1]",
            "citations": {"status": "matched"},
        }
        self.footer = {"completed_records": 1, "errors": 0}

    def stats(self, record):
        return summarize_records(self.metadata, [record], self.footer)["modes"]["guarded"]["stats"]

    def test_screened_attack_is_distinct_from_model_exposure(self):
        stats = self.stats(self.record)
        self.assertEqual(stats["target_retrieved"], 1)
        self.assertEqual(stats["target_exposed"], 0)
        self.assertEqual(stats["attack_screened_out"], 1)
        self.assertEqual(stats["target_marker_outputs"], 0)

    def test_attack_never_retrieved_is_not_counted_as_exposed(self):
        self.record["retrieved_ids"] = ["clean:1"]
        self.record["blocked"] = []
        stats = self.stats(self.record)
        self.assertEqual(stats["attack_cases"], 1)
        self.assertEqual(stats["target_retrieved"], 0)
        self.assertEqual(stats["target_exposed"], 0)
        self.assertEqual(fraction(0, stats["target_exposed"]), "N/A (0/0)")

    def test_exposed_marker_output_is_counted(self):
        self.record["context_ids"] = ["clean:1", "attack:1"]
        self.record["blocked"] = []
        self.record["answer"] = "DEMO-MARKER"
        stats = self.stats(self.record)
        self.assertEqual(stats["exposed_target_marker_outputs"], 1)
        self.assertEqual(stats["any_marker_outputs"], 1)

    def test_benign_screening_uses_retrieval_occurrences(self):
        self.record["blocked"] = [{"id": "clean:1"}]
        self.record["context_ids"] = ["attack:1"]
        stats = self.stats(self.record)
        self.assertEqual(stats["benign_retrievals"], 1)
        self.assertEqual(stats["benign_screened_out"], 1)
        self.assertEqual(stats["reference_in_context"], 0)

    def test_access_source_and_answer_text_are_measured_separately(self):
        self.record["case"]["forbidden_source_ids"] = ["attack:1"]
        self.record["case"]["forbidden_answer_text"] = ["SECRET"]
        self.record["answer"] = "secret"
        stats = self.stats(self.record)
        self.assertEqual(stats["access_checks"], 1)
        self.assertEqual(stats["forbidden_source_outputs"], 1)
        self.assertEqual(stats["forbidden_text_outputs"], 1)

    def test_model_error_is_excluded_from_attack_denominator(self):
        self.record = {
            "case": self.record["case"], "defense": "guarded", "status": "error", "elapsed_seconds": 1.0,
        }
        summary = summarize_records(self.metadata, [self.record], {"completed_records": 1, "errors": 1})
        self.assertEqual(summary["errors"], 1)
        self.assertEqual(summary["modes"]["guarded"]["stats"]["attack_cases"], 0)

    def test_missing_footer_marks_run_unfinished(self):
        summary = summarize_records(self.metadata, [self.record], None)
        self.assertFalse(summary["finished"])

    def test_duplicate_case_mode_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            summarize_records(self.metadata, [self.record, copy.deepcopy(self.record)], None)

    def test_invalid_context_sources_are_rejected(self):
        self.record["context_ids"] = ["outside:1"]
        with self.assertRaisesRegex(ValueError, "inconsistent"):
            self.stats(self.record)

    def test_inaccurate_footer_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "footer disagrees"):
            summarize_records(self.metadata, [self.record], {"completed_records": 2, "errors": 0})

    def test_older_runs_without_marker_catalog_remain_readable(self):
        del self.metadata["attack_markers"]
        summary = summarize_records(self.metadata, [self.record], self.footer)
        self.assertFalse(summary["markers_available"])
        self.assertTrue(summary["finished"])
