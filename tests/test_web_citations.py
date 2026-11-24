import copy
import unittest
from unittest.mock import patch

from app import app
from citations import check_citations
from ingest import load_chunks
from web_citations import citation_parts


class CitationDisplayTests(unittest.TestCase):
    def setUp(self):
        self.chunks = [{"id": "faq:1"}, {"id": "faq:2"}]

    def test_numbers_match_context_order_even_when_answer_cites_second_source_first(self):
        self.assertEqual(citation_parts("Answer [faq:2].", self.chunks),
                         [{"text": "Answer "}, {"number": 2}, {"text": "."}])

    def test_bracket_groups_and_repeated_ids_share_the_same_numbers(self):
        for separator in (", ", "; ", " "):
            with self.subTest(separator=separator):
                parts = citation_parts(f"[faq:1{separator}faq:2] [faq:1]", self.chunks)
                self.assertEqual([p["number"] for p in parts if "number" in p], [1, 2, 1])
                self.assertEqual([p["text"] for p in parts if "text" in p], [" ", " "])

    def test_bare_source_id_is_formatted_without_dropping_surrounding_text(self):
        self.assertEqual(citation_parts("Source: faq:1\nDone.", self.chunks),
                         [{"text": "Source: "}, {"number": 1}, {"text": "\nDone."}])

    def test_unknown_or_forbidden_id_never_becomes_a_numbered_reference(self):
        self.assertEqual(citation_parts("[recovery-procedure:1]", self.chunks),
                         [{"text": "[unverified source]"}])

    def test_mixed_known_and_unknown_group_keeps_unknown_unverified(self):
        self.assertEqual(citation_parts("[faq:2, missing:1]", self.chunks),
                         [{"number": 2}, {"text": " "}, {"text": "[unverified source]"}])

    def test_invalid_prefix_matches_are_not_rewritten_as_known_sources(self):
        text = "[faq:1x] [faq:1-other] [1]"
        self.assertEqual(citation_parts(text, self.chunks), [{"text": text}])

    def test_raw_answer_and_chunks_are_not_modified(self):
        chunks = copy.deepcopy(self.chunks)
        answer = "<script>untrusted</script> [faq:1]"
        before = check_citations(answer, chunks)
        parts = citation_parts(answer, chunks)
        self.assertEqual(parts[0]["text"], "<script>untrusted</script> ")
        self.assertEqual(chunks, self.chunks)
        self.assertEqual(check_citations(answer, chunks), before)
        self.assertEqual(answer, "<script>untrusted</script> [faq:1]")

    def test_no_source_id_adds_no_reference(self):
        self.assertEqual(citation_parts("I do not have enough information.", []),
                         [{"text": "I do not have enough information."}])


class WebCitationRenderingTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.client.get("/login")
        with self.client.session_transaction() as session:
            token = session["csrf_token"]
        self.client.post("/login", data={"username": "employee", "password": "employee-demo", "csrf_token": token})
        self.chunk = next(c for c in load_chunks() if c["id"] == "support-faq:1")

    def ask(self, answer):
        reply = {"answer": answer, "chunks": [self.chunk], "retrieved_chunks": [self.chunk],
                 "blocked": [], "citations": check_citations(answer, [self.chunk])}
        with self.client.session_transaction() as session:
            token = session["csrf_token"]
        with patch("app.answer_question", return_value=reply):
            response = self.client.post("/chat", data={"question": "VPN?", "csrf_token": token})
        return response.json["html"], reply

    def test_answer_button_points_to_source_in_same_fragment_and_retains_raw_id_in_details(self):
        html, reply = self.ask("Use the portal [support-faq:1].")
        answer = html.split('<div class="answer-text">', 1)[1].split('</div>', 1)[0]
        self.assertIn('class="citation-ref" data-source-number="1"', answer)
        self.assertIn('>[1]</button>', answer)
        self.assertNotIn("support-faq:1", answer)
        self.assertIn('class="source-card" data-source-number="1"', html)
        self.assertIn("Source ID: [support-faq:1]", html)
        self.assertEqual(reply["answer"], "Use the portal [support-faq:1].")

    def test_unknown_id_is_visible_as_unverified_without_click_target_or_document_lookup(self):
        html, _ = self.ask("See [recovery-procedure:1].")
        answer = html.split('<div class="answer-text">', 1)[1].split('</div>', 1)[0]
        self.assertIn("[unverified source]", answer)
        self.assertNotIn('class="citation-ref"', answer)
        self.assertIn("Unmatched source IDs: recovery-procedure:1", html)
        self.assertNotIn("DEMO-RECOVERY-47", html)

    def test_citation_formatting_does_not_make_model_markup_executable(self):
        html, _ = self.ask('<button onclick="alert(1)">bad</button> [support-faq:1]')
        self.assertNotIn('<button onclick=', html)
        self.assertIn('&lt;button onclick=', html)
        self.assertIn('class="citation-ref"', html)

    def test_numbers_restart_for_each_response_without_shared_document_ids(self):
        first, _ = self.ask("First [support-faq:1]")
        second, _ = self.ask("Second [support-faq:1]")
        for html in (first, second):
            self.assertIn('aria-label="Show source 1"', html)
            self.assertNotIn(' id="', html)
