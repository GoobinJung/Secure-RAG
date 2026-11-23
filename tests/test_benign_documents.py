import unittest

from ingest import load_chunks
from safeguards import inspect_chunk, screen_chunks


class BenignDocumentTests(unittest.TestCase):
    def setUp(self):
        self.chunks = {chunk["id"]: chunk for chunk in load_chunks()}

    def test_training_quote_demonstrates_instruction_pattern_false_positive(self):
        chunk = self.chunks["security-training:1"]
        self.assertEqual(chunk["style"], "policy")
        self.assertIn('quoted sentence "Ignore previous instructions"', chunk["text"])
        self.assertIn("security reporting form", chunk["text"])
        self.assertEqual(inspect_chunk(chunk["text"]), "instruction_override")

    def test_log_label_demonstrates_role_pattern_false_positive(self):
        chunk = self.chunks["document-safety-faq:1"]
        self.assertEqual(chunk["style"], "faq")
        self.assertIn("event source label", chunk["text"])
        self.assertEqual(inspect_chunk(chunk["text"]), "role_impersonation")

    def test_routine_faq_and_service_note_are_retained(self):
        chunks = [self.chunks["document-safety-faq:2"], self.chunks["routine-service-note:1"]]
        approved, blocked = screen_chunks(chunks)
        self.assertEqual(approved, chunks)
        self.assertEqual(blocked, [])
        self.assertIn("2026-11-15T09:30:00Z", chunks[1]["text"])

    def test_benign_examples_inherit_public_test_permissions(self):
        for chunk_id in (
            "security-training:1", "document-safety-faq:1",
            "document-safety-faq:2", "routine-service-note:1",
        ):
            with self.subTest(chunk_id=chunk_id):
                chunk = self.chunks[chunk_id]
                self.assertEqual(chunk["roles"], ["employee", "admin"])
                self.assertNotIn("DEMO-", chunk["text"])
