import unittest
from unittest.mock import patch

from app import app


class WebRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def token(self):
        with self.client.session_transaction() as session:
            return session["csrf_token"]

    def sign_in(self):
        self.client.get("/login")
        self.client.post("/login", data={
            "username": "employee", "password": "employee-demo", "csrf_token": self.token(),
        })

    def test_stale_login_form_has_recovery_link_and_retains_error_status(self):
        self.client.get("/login")
        old_token = self.token()
        self.sign_in()
        with patch("app.answer_question") as answer:
            response = self.client.post("/login", data={
                "username": "admin", "password": "admin-demo", "csrf_token": old_token,
            })
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"Please reload the form", response.data)
        self.assertIn(b'Return to the app</a>', response.data)
        with self.client.session_transaction() as session:
            self.assertEqual(session["username"], "employee")
        answer.assert_not_called()

    def test_expired_session_question_can_recover_to_login(self):
        self.sign_in()
        old_token = self.token()
        with self.client.session_transaction() as session:
            session.clear()
        with patch("app.answer_question") as answer:
            response = self.client.post("/", data={"question": "VPN?", "csrf_token": old_token})
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"You may need to sign in again.", response.data)
        self.assertEqual(self.client.get("/", follow_redirects=True).status_code, 200)
        self.assertIn(b'name="password"', self.client.get("/login").data)
        answer.assert_not_called()

    def test_oversized_form_is_rejected_before_any_model_call(self):
        self.sign_in()
        with patch("app.answer_question") as answer:
            response = self.client.post("/", data={
                "csrf_token": self.token(), "question": "x" * (64 * 1024),
            })
        self.assertEqual(response.status_code, 413)
        self.assertIn(b"Request too large", response.data)
        self.assertIn(b"Return to the app", response.data)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertIn("frame-ancestors 'none'", response.headers["Content-Security-Policy"])
        answer.assert_not_called()

    def test_signed_out_oversized_login_has_public_recovery_page(self):
        response = self.client.post("/login", data={"username": "x" * (64 * 1024)})
        self.assertEqual(response.status_code, 413)
        self.assertIn(b"Request too large", response.data)
        self.assertNotIn(b"Traceback", response.data)
        self.assertNotIn(b"Sign out", response.data)

    def test_fresh_login_succeeds_after_invalid_token(self):
        self.client.get("/login")
        invalid = self.client.post("/login", data={
            "username": "employee", "password": "employee-demo", "csrf_token": "stale",
        })
        self.assertEqual(invalid.status_code, 400)
        self.sign_in()
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'id="account-role">employee</dd>', response.data)

    def test_model_failure_allows_retry_with_same_question_and_mode(self):
        self.sign_in()
        form = {"question": "VPN service?", "defense": "baseline", "csrf_token": self.token()}
        reply = {
            "answer": "I do not have enough information.", "chunks": [],
            "retrieved_chunks": [], "blocked": [],
            "citations": {"status": "missing", "cited_ids": [], "unknown_ids": []},
        }
        with patch("app.answer_question", side_effect=[RuntimeError("Open Ollama and retry."), reply]) as answer:
            failed = self.client.post("/", data=form)
            recovered = self.client.post("/", data=form)
        self.assertEqual(failed.status_code, 502)
        self.assertIn(b"Open Ollama and retry.", failed.data)
        self.assertIn(b"VPN service?", failed.data)
        self.assertIn(b'value="baseline" selected', failed.data)
        self.assertNotIn(b'class="answer-text"', failed.data)
        self.assertEqual(recovered.status_code, 200)
        self.assertIn(reply["answer"].encode(), recovered.data)
        self.assertEqual(answer.call_count, 2)
        self.assertEqual(answer.call_args.args, ("VPN service?", "employee"))

    def test_no_answer_or_document_text_is_stored_in_session(self):
        self.sign_in()
        reply = {
            "answer": "UNIQUE-ANSWER-FOR-THIS-TEST", "chunks": [],
            "retrieved_chunks": [], "blocked": [],
            "citations": {"status": "missing", "cited_ids": [], "unknown_ids": []},
        }
        with patch("app.answer_question", return_value=reply):
            self.client.post("/", data={"question": "UNIQUE-QUESTION-FOR-THIS-TEST", "csrf_token": self.token()})
        with self.client.session_transaction() as session:
            self.assertEqual(set(session), {"username", "csrf_token", "_permanent"})
            self.assertNotIn("UNIQUE-", str(dict(session)))
