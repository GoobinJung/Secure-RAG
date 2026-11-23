import unittest
from unittest.mock import patch

from app import app


class WebQuestionTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.reply = {"answer": "Submit a request. [support-faq:1]"}

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
        with patch("app.answer_question", return_value={"answer": '<script>alert("test")</script>'}):
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
