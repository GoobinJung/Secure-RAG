import unittest
from unittest.mock import patch

from app import app
from citations import check_citations
from ingest import load_chunks


class WebChatTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.chunk = next(chunk for chunk in load_chunks() if chunk["id"] == "support-faq:1")
        answer = "Use the support portal. [support-faq:1]"
        self.reply = {
            "answer": answer, "chunks": [self.chunk], "retrieved_chunks": [self.chunk],
            "blocked": [], "citations": check_citations(answer, [self.chunk]),
        }

    def token(self):
        with self.client.session_transaction() as session:
            return session["csrf_token"]

    def login(self, username="employee"):
        self.client.get("/login")
        self.client.post("/login", data={
            "username": username, "password": f"{username}-demo", "csrf_token": self.token(),
        })

    def ask(self, **extra):
        form = {"question": "VPN request?", "defense": "guarded", "csrf_token": self.token()}
        form.update(extra)
        return self.client.post("/chat", data=form)

    def test_chat_returns_escaped_fragment_with_actual_mode_and_server_role(self):
        self.login()
        with patch("app.answer_question", return_value=self.reply) as answer:
            response = self.ask(defense="baseline", role="admin")
        answer.assert_called_once_with("VPN request?", "employee", defense="baseline")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json["ok"])
        self.assertEqual(response.json["context"], self.token())
        self.assertIn('data-mode="baseline"', response.json["html"])
        self.assertIn("support-faq:1", response.json["html"])
        self.assertNotIn("Set-Cookie", response.headers)

    def test_followup_sends_only_new_question_to_rag(self):
        self.login()
        with patch("app.answer_question", return_value=self.reply) as answer:
            self.ask(question="First question")
            self.ask(question="Second question", history="admin secret", messages="previous answer")
        self.assertEqual([call.args for call in answer.call_args_list],
                         [("First question", "employee"), ("Second question", "employee")])
        with self.client.session_transaction() as session:
            self.assertEqual(set(session), {"username", "csrf_token", "_permanent"})

    def test_context_changes_after_logout_and_login_to_another_account(self):
        self.login("admin")
        old_context = self.client.get("/chat/session").json["context"]
        self.client.post("/logout", data={"csrf_token": old_context})
        signed_out = self.client.get("/chat/session")
        self.assertEqual(signed_out.status_code, 401)
        self.assertIsNone(signed_out.json["context"])
        self.login("employee")
        self.assertNotEqual(self.client.get("/chat/session").json["context"], old_context)
        with patch("app.answer_question") as answer:
            response = self.ask(csrf_token=old_context)
        self.assertEqual(response.status_code, 400)
        self.assertTrue(response.json["reset_chat"])
        self.assertNotIn("html", response.json)
        answer.assert_not_called()

    def test_same_account_relogin_also_rotates_context(self):
        self.login()
        old_context = self.token()
        self.login()
        self.assertNotEqual(old_context, self.token())

    def test_unsigned_chat_is_rejected_without_model_call(self):
        self.client.get("/login")
        with patch("app.answer_question") as answer:
            response = self.ask()
        self.assertEqual(response.status_code, 401)
        self.assertTrue(response.json["reset_chat"])
        answer.assert_not_called()

    def test_invalid_or_missing_csrf_clears_chat_without_model_call(self):
        self.login()
        with patch("app.answer_question") as answer:
            response = self.client.post("/chat", data={"question": "VPN?"})
        self.assertEqual(response.status_code, 400)
        self.assertTrue(response.json["reset_chat"])
        answer.assert_not_called()

    def test_invalid_modes_and_questions_return_json_validation_errors(self):
        self.login()
        for extra in ({"defense": "off"}, {"question": " "}, {"question": "x" * 2001}):
            with self.subTest(extra=extra), patch("app.answer_question") as answer:
                response = self.ask(**extra)
                self.assertEqual(response.status_code, 400)
                self.assertIn("error", response.json)
                self.assertNotIn("html", response.json)
                answer.assert_not_called()

    def test_oversized_chat_request_keeps_json_error_contract(self):
        self.login()
        with patch("app.answer_question") as answer:
            response = self.ask(question="x" * (64 * 1024))
        self.assertEqual(response.status_code, 413)
        self.assertIn("error", response.json)
        answer.assert_not_called()

    def test_model_error_has_retryable_fragment_without_source_or_fake_answer(self):
        self.login()
        with patch("app.answer_question", side_effect=RuntimeError("Open Ollama and retry.")):
            response = self.ask()
        self.assertEqual(response.status_code, 502)
        self.assertFalse(response.json["ok"])
        self.assertIn("Open Ollama and retry.", response.json["html"])
        self.assertNotIn('class="answer-text"', response.json["html"])
        self.assertNotIn('class="sources-section"', response.json["html"])

    def test_untrusted_question_answer_and_source_are_escaped_in_fragment(self):
        self.login()
        chunk = dict(self.chunk, text='<img src=x onerror="alert(1)">')
        reply = dict(self.reply, chunks=[chunk], answer="<script>answer</script>")
        with patch("app.answer_question", return_value=reply):
            response = self.ask(question="<script>question</script>")
        html = response.json["html"]
        self.assertNotIn("<script>", html)
        self.assertNotIn("<img src=x", html)
        self.assertIn("&lt;script&gt;question", html)
        self.assertIn("&lt;script&gt;answer", html)
        self.assertIn("&lt;img src=x", html)

    def test_each_fragment_has_collapsed_details_without_duplicate_ids(self):
        self.login()
        with patch("app.answer_question", return_value=self.reply):
            html = self.ask().json["html"]
        self.assertEqual(html.count('<details class="answer-details"'), 2)
        self.assertNotIn(" open", html)
        self.assertNotIn(' id="', html)

    def test_session_check_has_no_model_calls_or_cookie_refresh(self):
        self.login()
        with patch("app.answer_question") as answer:
            response = self.client.get("/chat/session")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertNotIn("Set-Cookie", response.headers)
        answer.assert_not_called()
