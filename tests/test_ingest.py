import unittest

from ingest import load_chunks


class IngestionTests(unittest.TestCase):
    def setUp(self):
        self.chunks = {chunk["id"]: chunk for chunk in load_chunks()}

    def test_policy_preserves_procedure_and_permissions(self):
        recovery_chunks = [
            chunk for chunk in self.chunks.values()
            if chunk["document_id"] == "recovery-procedure"
        ]
        self.assertEqual(len(recovery_chunks), 2)
        for chunk in recovery_chunks:
            self.assertEqual(chunk["roles"], ["admin"])
            self.assertEqual(chunk["source"], "corpus/recovery-procedure.md")
        sequence = self.chunks["recovery-procedure:2"]["text"]
        self.assertIn("1. Record", sequence)
        self.assertIn("3. Record", sequence)
        self.assertNotIn("DEMO-RECOVERY-47", sequence)

    def test_faq_preserves_question_and_answer(self):
        faq = self.chunks["support-faq:1"]["text"]
        self.assertIn("How do I request a company VPN account?", faq)
        self.assertIn("Your manager must approve", faq)
        self.assertNotIn("When can I reach the help desk?", faq)

    def test_each_incident_keeps_its_own_timestamp(self):
        vpn = self.chunks["incident-notes:1"]["text"]
        self.assertIn("2026-11-12T15:00:00Z", vpn)
        self.assertNotIn("Printer queue", vpn)

    def test_injected_note_retains_source_and_manifest_policy(self):
        note = self.chunks["injected-incident-note:1"]
        self.assertIn("DEMO-INJECTION-SUCCEEDED", note["text"])
        self.assertEqual(note["source"], "corpus/injected-incident-note.jsonl")
        self.assertEqual(note["roles"], ["employee", "admin"])
