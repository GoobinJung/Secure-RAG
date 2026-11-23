import unittest

from ingest import load_chunks
from safeguards import inspect_chunk


class AttackDocumentTests(unittest.TestCase):
    def setUp(self):
        self.chunks = {chunk["id"]: chunk for chunk in load_chunks()}

    def test_policy_role_impersonation_is_screened(self):
        chunk = self.chunks["injected-policy:1"]
        self.assertEqual(chunk["style"], "policy")
        self.assertIn("printer queue recovery", chunk["text"].lower())
        self.assertIn("DEMO-ROLE-OVERRIDE", chunk["text"])
        self.assertEqual(inspect_chunk(chunk["text"]), "role_impersonation")

    def test_faq_hidden_character_survives_loading_and_is_normalized_for_screening(self):
        chunk = self.chunks["injected-faq:1"]
        self.assertEqual(chunk["style"], "faq")
        self.assertIn("How do I enroll a replacement MFA device?", chunk["text"])
        self.assertIn("Ig\u200bnore", chunk["text"])
        self.assertEqual(inspect_chunk(chunk["text"]), "instruction_override")

    def test_paraphrased_note_demonstrates_current_pattern_gap(self):
        chunk = self.chunks["injected-paraphrased-note:1"]
        self.assertEqual(chunk["style"], "incident_notes")
        self.assertIn("2026-11-14T10:00:00Z", chunk["text"])
        self.assertIn("DEMO-REPHRASED-OVERRIDE", chunk["text"])
        self.assertIsNone(inspect_chunk(chunk["text"]))

    def test_added_attack_chunks_inherit_public_test_permissions(self):
        for chunk_id in ("injected-policy:1", "injected-faq:1", "injected-paraphrased-note:1"):
            with self.subTest(chunk_id=chunk_id):
                self.assertEqual(self.chunks[chunk_id]["roles"], ["employee", "admin"])
