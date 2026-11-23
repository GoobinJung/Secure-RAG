import json
import unittest
from unittest.mock import patch

from app import app
from citations import check_citations
from ingest import load_chunks


class WebQuestionTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.chunks = {chunk["id"]: chunk for chunk in load_chunks()}
        context = [self.chunks["support-faq:1"]]
        answer = "Submit a request. [support-faq:1]"
        self.reply = {
            "answer": answer, "chunks": context, "retrieved_chunks": context,
            "blocked": [], "citations": check_citations(answer, context),
        }

    def sign_in(self, username="employee", password="employee-demo"):
        self.client.get("/login")
        with self.client.session_transaction() as session:
            token = session["csrf_token"]
        self.client.post("/login", data={
            "username": username, "password": password, "csrf_token": token,
        })

    def ask(self, question="How do I request a VPN account?", **extra):
        with self.client.session_transaction() as session:
            token = session["csrf_token"]
        data = {"question": question, "csrf_token": token}
        data.update(extra)
        return self.client.post("/", data=data)

    def test_employee_question_uses_server_role_and_guarded_mode(self):
        self.sign_in()
        with patch("app.answer_question", return_value=self.reply) as answer:
            response = self.ask(role="admin", defense="baseline")
        answer.assert_called_once_with("How do I request a VPN account?", "employee", defense="guarded")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Submit a request.", response.data)

    def test_admin_question_uses_admin_role(self):
        self.sign_in("admin", "admin-demo")
        with patch("app.answer_question", return_value=self.reply) as answer:
            self.ask()
        self.assertEqual(answer.call_args.args[1], "admin")

    def test_signed_out_question_never_calls_the_model(self):
        self.client.get("/login")
        with patch("app.answer_question") as answer:
            response = self.ask()
        self.assertEqual(response.status_code, 302)
        answer.assert_not_called()

    def test_question_requires_csrf_token(self):
        self.sign_in()
        with patch("app.answer_question") as answer:
            response = self.client.post("/", data={"question": "VPN"})
        self.assertEqual(response.status_code, 400)
        answer.assert_not_called()

    def test_blank_and_overlong_questions_are_rejected(self):
        self.sign_in()
        for question in ("   ", "x" * 2001):
            with self.subTest(length=len(question)), patch("app.answer_question") as answer:
                response = self.ask(question)
                self.assertEqual(response.status_code, 400)
                answer.assert_not_called()

    def test_question_is_trimmed_before_model_request(self):
        self.sign_in()
        with patch("app.answer_question", return_value=self.reply) as answer:
            self.ask("  VPN request?  ")
        self.assertEqual(answer.call_args.args[0], "VPN request?")

    def test_model_failure_is_displayed_and_question_is_preserved(self):
        self.sign_in()
        with patch("app.answer_question", side_effect=RuntimeError("Open Ollama and retry.")):
            response = self.ask("How do I request a VPN account?")
        self.assertEqual(response.status_code, 502)
        self.assertIn(b"Open Ollama and retry.", response.data)
        self.assertIn(b"How do I request a VPN account?", response.data)

    def test_model_output_is_escaped_in_html(self):
        self.sign_in()
        reply = dict(self.reply, answer='<script>alert("test")</script>')
        with patch("app.answer_question", return_value=reply):
            response = self.ask()
        self.assertNotIn(b'<script>alert(', response.data)
        self.assertIn(b"&lt;script&gt;", response.data)

    def test_question_cannot_close_textarea_and_inject_html(self):
        self.sign_in()
        with patch("app.answer_question", return_value=self.reply):
            response = self.ask('</textarea><script>alert("test")</script>')
        self.assertNotIn(b'</textarea><script>alert(', response.data)
        self.assertIn(b"&lt;/textarea&gt;", response.data)

    def test_question_page_get_does_not_call_model(self):
        self.sign_in()
        with patch("app.answer_question") as answer:
            response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'id="question-form"', response.data)
        answer.assert_not_called()

    def test_source_details_show_exact_context_text_and_metadata(self):
        self.sign_in()
        with patch("app.answer_question", return_value=self.reply):
            response = self.ask()
        self.assertIn(b"<details", response.data)
        self.assertIn(b"[support-faq:1]", response.data)
        self.assertIn(b"corpus/support-faq.json", response.data)
        self.assertIn(self.chunks["support-faq:1"]["text"].encode(), response.data)
        self.assertIn(b"all cited source IDs were supplied", response.data)
        self.assertIn(b"This checks source IDs only.", response.data)

    def test_screened_out_text_is_not_rendered_as_a_source(self):
        self.sign_in()
        blocked = self.chunks["injected-incident-note:1"]
        reply = dict(self.reply, retrieved_chunks=self.reply["chunks"] + [blocked], blocked=[{
            "id": blocked["id"], "source": blocked["source"], "reason": "instruction_override",
        }])
        with patch("app.answer_question", return_value=reply):
            response = self.ask()
        self.assertNotIn(b"DEMO-INJECTION-SUCCEEDED", response.data)
        self.assertNotIn(b"corpus/injected-incident-note.jsonl", response.data)

    def test_uncited_context_is_still_available_for_inspection(self):
        self.sign_in()
        reply = dict(self.reply, chunks=self.reply["chunks"] + [self.chunks["support-faq:2"]])
        with patch("app.answer_question", return_value=reply):
            response = self.ask()
        self.assertIn(b"[support-faq:2]", response.data)

    def test_unknown_citation_is_reported_without_loading_its_document(self):
        self.sign_in()
        answer = "See [recovery-procedure:1]."
        reply = dict(self.reply, answer=answer, citations=check_citations(answer, self.reply["chunks"]))
        with patch("app.answer_question", return_value=reply):
            response = self.ask()
        self.assertIn(b"Unmatched source IDs: recovery-procedure:1", response.data)
        self.assertNotIn(b"DEMO-RECOVERY-47", response.data)
        self.assertNotIn(b"corpus/recovery-procedure.md", response.data)

    def test_missing_citation_is_reported_with_context_available(self):
        self.sign_in()
        answer = "Submit a request."
        reply = dict(self.reply, answer=answer, citations=check_citations(answer, self.reply["chunks"]))
        with patch("app.answer_question", return_value=reply):
            response = self.ask()
        self.assertIn(b"no source IDs found in the answer", response.data)
        self.assertIn(b"corpus/support-faq.json", response.data)

    def test_empty_context_displays_no_source_message(self):
        self.sign_in()
        reply = dict(self.reply, answer="No usable source documents available for this question.",
                     chunks=[], citations=check_citations("", []))
        with patch("app.answer_question", return_value=reply):
            response = self.ask()
        self.assertIn(b"No document excerpts were sent to the answer model.", response.data)
        self.assertNotIn(b'<details class="source-card">', response.data)

    def test_source_metadata_and_content_are_escaped(self):
        self.sign_in()
        chunk = dict(self.chunks["support-faq:1"], title="<img src=x onerror=alert(1)>",
                     source="<script>path</script>", text="<script>source text</script>")
        with patch("app.answer_question", return_value=dict(self.reply, chunks=[chunk])):
            response = self.ask()
        self.assertNotIn(b"<img src=x", response.data)
        self.assertNotIn(b"<script>source text", response.data)
        self.assertIn(b"&lt;script&gt;source text&lt;/script&gt;", response.data)
        self.assertIn(b"&lt;script&gt;path&lt;/script&gt;", response.data)
        self.assertIn(b"&lt;img src=x", response.data)

    def test_real_rag_pipeline_keeps_restricted_sources_out_of_employee_html(self):
        def model_reply(endpoint, payload):
            if endpoint == "embed":
                vectors = [[1.0, 0.0]]
                vectors.extend([1.0, 0.0] if "Administrator Recovery Procedure" in text
                               else [0.0, 1.0] for text in payload["input"][1:])
                return {"embeddings": vectors}
            sources = json.loads(payload["messages"][1]["content"])["sources"]
            available = {source["id"] for source in sources}
            answer = ("DEMO-RECOVERY-47 [recovery-procedure:1]" if "recovery-procedure:1" in available
                      else "I do not have enough information.")
            return {"done": True, "message": {"content": answer}}

        for username in ("employee", "admin"):
            with self.subTest(role=username):
                self.sign_in(username, f"{username}-demo")
                with patch("rag.request_ollama", side_effect=model_reply):
                    response = self.ask("What is the administrator emergency recovery code?")
                self.assertEqual(response.status_code, 200)
                for restricted in (b"DEMO-RECOVERY-47", b"corpus/recovery-procedure.md"):
                    if username == "employee":
                        self.assertNotIn(restricted, response.data)
                    else:
                        self.assertIn(restricted, response.data)
