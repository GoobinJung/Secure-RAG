import unittest

from evaluation_cases import load_evaluation_cases, validate_cases
from ingest import load_chunks


class EvaluationCaseTests(unittest.TestCase):
    def setUp(self):
        self.data = load_evaluation_cases()
        self.chunks = {chunk["id"]: chunk for chunk in load_chunks()}

    def test_duplicate_case_ids_are_rejected(self):
        self.data["cases"].append(self.data["cases"][0])
        with self.assertRaisesRegex(ValueError, "unique"):
            validate_cases(self.data, self.chunks)

    def test_unknown_source_reference_is_rejected(self):
        self.data["cases"][0]["reference_source_ids"] = ["unknown:1"]
        with self.assertRaisesRegex(ValueError, "Unknown source"):
            validate_cases(self.data, self.chunks)

    def test_employee_reference_cannot_use_admin_document(self):
        self.data["cases"][0]["reference_source_ids"] = ["recovery-procedure:1"]
        with self.assertRaisesRegex(ValueError, "restricted source"):
            validate_cases(self.data, self.chunks)

    def test_attack_marker_must_exist_in_its_source(self):
        case = next(case for case in self.data["cases"] if case["category"] == "attack")
        case["attack"]["marker"] = "MISSING-MARKER"
        with self.assertRaisesRegex(ValueError, "Attack marker"):
            validate_cases(self.data, self.chunks)

    def test_removed_or_added_corpus_chunks_require_label_update(self):
        del self.data["source_labels"]["support-faq:1"]
        with self.assertRaisesRegex(ValueError, "cover the current corpus"):
            validate_cases(self.data, self.chunks)

    def test_empty_case_set_is_rejected(self):
        self.data["cases"] = []
        with self.assertRaisesRegex(ValueError, "must contain cases"):
            validate_cases(self.data, self.chunks)

    def test_authorized_source_cannot_be_marked_forbidden(self):
        self.data["cases"][0]["forbidden_source_ids"] = ["support-faq:1"]
        with self.assertRaisesRegex(ValueError, "Forbidden source is authorized"):
            validate_cases(self.data, self.chunks)
