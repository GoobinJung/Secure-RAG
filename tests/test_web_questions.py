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

    def test_employee_question_uses_server_role_and_defaults_to_guarded(self):
        self.sign_in()
        with patch("app.answer_question", return_value=self.reply) as answer:
            response = self.ask(role="admin")
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
        source_panel = response.data.split(b'class="sources-section"', 1)[1]
        self.assertNotIn(b"corpus/injected-incident-note.jsonl", source_panel)
        self.assertIn(b"corpus/injected-incident-note.jsonl", response.data)

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
            for defense in ("baseline", "guarded"):
                with self.subTest(role=username, defense=defense):
                    self.sign_in(username, f"{username}-demo")
                    with patch("rag.request_ollama", side_effect=model_reply):
                        response = self.ask("What is the administrator emergency recovery code?", defense=defense)
                    self.assertEqual(response.status_code, 200)
                    for restricted in (b"DEMO-RECOVERY-47", b"corpus/recovery-procedure.md"):
                        if username == "employee":
                            self.assertNotIn(restricted, response.data)
                        else:
                            self.assertIn(restricted, response.data)

    def test_baseline_selection_preserves_employee_role(self):
        self.sign_in()
        with patch("app.answer_question", return_value=self.reply) as answer:
            response = self.ask(defense="baseline", role="admin")
        answer.assert_called_once_with("How do I request a VPN account?", "employee", defense="baseline")
        self.assertIn(b'value="baseline" selected', response.data)
        self.assertIn(b"Mode used: <strong>Baseline</strong>", response.data)
        self.assertIn(b"Pattern screening was not applied.", response.data)
        self.assertNotIn(b"No current screening patterns matched", response.data)

    def test_explicit_guarded_selection_is_used(self):
        self.sign_in()
        with patch("app.answer_question", return_value=self.reply) as answer:
            response = self.ask(defense="guarded")
        self.assertEqual(answer.call_args.kwargs["defense"], "guarded")
        self.assertIn(b'value="guarded" selected', response.data)
        self.assertIn(b"No current screening patterns matched", response.data)
        self.assertIn(b"Unmatched text can still contain an attack.", response.data)

    def test_invalid_modes_are_rejected_before_model_call(self):
        self.sign_in()
        for mode in ("", "disabled", "GUARDED", "<script>test</script>"):
            with self.subTest(mode=mode), patch("app.answer_question") as answer:
                response = self.ask(defense=mode)
                self.assertEqual(response.status_code, 400)
                self.assertIn(b"Choose Baseline or Guarded mode.", response.data)
                self.assertNotIn(b"<script>test</script>", response.data)
                answer.assert_not_called()

    def test_mode_and_question_survive_model_failure(self):
        self.sign_in()
        with patch("app.answer_question", side_effect=RuntimeError("Ollama unavailable.")):
            response = self.ask("VPN service?", defense="baseline")
        self.assertEqual(response.status_code, 502)
        self.assertIn(b'value="baseline" selected', response.data)
        self.assertIn(b"VPN service?", response.data)
        self.assertNotIn(b'class="screening-section"', response.data)

    def test_screening_panel_reports_reasons_without_exposing_blocked_text(self):
        self.sign_in()
        for reason, description in (
            ("instruction_override", b"ignore earlier instructions"),
            ("role_impersonation", b"system or developer message"),
            ("answer_redirection", b"away from answering"),
        ):
            with self.subTest(reason=reason):
                blocked = self.chunks["injected-incident-note:1"]
                reply = dict(self.reply, retrieved_chunks=self.reply["chunks"] + [blocked], blocked=[{
                    "id": blocked["id"], "source": blocked["source"], "reason": reason,
                }])
                with patch("app.answer_question", return_value=reply):
                    response = self.ask(defense="guarded")
                self.assertIn(reason.encode(), response.data)
                self.assertIn(description, response.data)
                self.assertIn(b"Retrieved: 2 &middot; Sent to model: 1 &middot; Screened out: 1", response.data)
                self.assertNotIn(b"DEMO-INJECTION-SUCCEEDED", response.data)

    def test_screening_metadata_is_escaped(self):
        self.sign_in()
        blocked = {"id": "<script>id</script>", "source": "<img src=x>",
                   "reason": "<script>reason</script>"}
        with patch("app.answer_question", return_value=dict(self.reply, blocked=[blocked])):
            response = self.ask()
        self.assertNotIn(b"<script>id", response.data)
        self.assertNotIn(b"<img src=x>", response.data)
        self.assertIn(b"&lt;script&gt;reason&lt;/script&gt;", response.data)

    def test_mode_change_drives_actual_rag_screening_with_stubbed_model(self):
        self.sign_in()
        injected = self.chunks["injected-incident-note:1"]["text"]
        clean = self.chunks["incident-notes:1"]["text"]
        contexts = {}

        def model_reply(endpoint, payload):
            if endpoint == "embed":
                vectors = [[1.0, 0.0]]
                for text in payload["input"][1:]:
                    vectors.append([1.0, 0.0] if clean in text else
                                   [0.9, 0.1] if injected in text else [0.0, 1.0])
                return {"embeddings": vectors}
            sources = json.loads(payload["messages"][1]["content"])["sources"]
            contexts[mode] = [source["id"] for source in sources]
            return {"done": True, "message": {"content": "Restarted the gateway. [incident-notes:1]"}}

        for mode in ("baseline", "guarded"):
            with patch("rag.request_ollama", side_effect=model_reply):
                response = self.ask("What resolved the VPN service interruption?", defense=mode)
            self.assertEqual(response.status_code, 200)
            if mode == "guarded":
                self.assertIn(b"instruction_override", response.data)
                self.assertNotIn(b"DEMO-INJECTION-SUCCEEDED", response.data)
            else:
                self.assertIn(b"DEMO-INJECTION-SUCCEEDED", response.data)
        self.assertIn("injected-incident-note:1", contexts["baseline"])
        self.assertNotIn("injected-incident-note:1", contexts["guarded"])
        self.assertIn("incident-notes:1", contexts["guarded"])
