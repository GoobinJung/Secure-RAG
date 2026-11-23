import unittest
from unittest.mock import patch

from app import app


class WebAuthenticationTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def token(self):
        self.client.get("/login")
        with self.client.session_transaction() as session:
            return session["csrf_token"]

    def login(self, username="employee", password="employee-demo", **extra_fields):
        data = {"username": username, "password": password, "csrf_token": self.token()}
        data.update(extra_fields)
        return self.client.post("/login", data=data)

    def test_signed_out_account_page_redirects_to_login(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.endswith("/login"))

    def test_login_page_contains_named_inputs_and_csrf_token(self):
        response = self.client.get("/login")
        for field in (b'name="username"', b'name="password"', b'name="csrf_token"'):
            self.assertIn(field, response.data)

    def test_valid_employee_login_stores_identity_and_resolves_role(self):
        self.assertEqual(self.login().status_code, 302)
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'id="account-role">employee</dd>', response.data)
        with self.client.session_transaction() as session:
            self.assertEqual(session["username"], "employee")
            self.assertNotIn("role", session)

    def test_admin_login_resolves_admin_role(self):
        self.login("admin", "admin-demo")
        self.assertIn(b'id="account-role">admin</dd>', self.client.get("/").data)

    def test_posted_role_cannot_promote_employee(self):
        self.login(role="admin")
        self.assertIn(b'id="account-role">employee</dd>', self.client.get("/?role=admin").data)

    def test_extra_session_role_does_not_override_account_mapping(self):
        self.login()
        with self.client.session_transaction() as session:
            session["role"] = "admin"
        self.assertIn(b'id="account-role">employee</dd>', self.client.get("/").data)

    def test_wrong_password_leaves_user_signed_out(self):
        response = self.login(password="wrong")
        self.assertEqual(response.status_code, 401)
        self.assertIn(b"Incorrect username or password.", response.data)
        self.assertEqual(self.client.get("/").status_code, 302)

    def test_unknown_user_gets_same_error(self):
        response = self.login(username="unknown")
        self.assertEqual(response.status_code, 401)
        self.assertIn(b"Incorrect username or password.", response.data)

    def test_login_requires_correct_form_token(self):
        response = self.client.post("/login", data={"username": "admin", "password": "admin-demo"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.get("/").status_code, 302)

    def test_unicode_form_token_is_rejected_cleanly(self):
        self.token()
        response = self.client.post("/login", data={
            "username": "employee", "password": "employee-demo", "csrf_token": "\uac00",
        })
        self.assertEqual(response.status_code, 400)

    def test_successful_login_rotates_token(self):
        old_token = self.token()
        self.client.post("/login", data={
            "username": "employee", "password": "employee-demo", "csrf_token": old_token,
        })
        with self.client.session_transaction() as session:
            self.assertNotEqual(session["csrf_token"], old_token)

    def test_logout_requires_token_and_clears_identity(self):
        self.login()
        self.assertEqual(self.client.post("/logout").status_code, 400)
        with self.client.session_transaction() as session:
            token = session["csrf_token"]
        self.assertEqual(self.client.post("/logout", data={"csrf_token": token}).status_code, 302)
        self.assertEqual(self.client.get("/").status_code, 302)

    def test_tampered_session_cookie_is_rejected(self):
        self.login()
        self.client.set_cookie(app.config["SESSION_COOKIE_NAME"], "modified-session")
        self.assertEqual(self.client.get("/").status_code, 302)

    def test_unknown_session_account_cannot_access_page(self):
        with self.client.session_transaction() as session:
            session["username"] = "unknown"
        self.assertEqual(self.client.get("/").status_code, 302)

    def test_login_pages_do_not_call_ollama_and_set_cookie_controls(self):
        with patch("rag.request_ollama") as model_request:
            response = self.client.get("/login")
            model_request.assert_not_called()
        self.assertIn("HttpOnly", response.headers["Set-Cookie"])
        self.assertIn("SameSite=Lax", response.headers["Set-Cookie"])
        self.assertEqual(response.headers["Cache-Control"], "no-store")

    def test_status_endpoint_keeps_original_status_response(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["server_status"], "running")
        self.assertEqual(response.json["answer_model"], "llama3.2:3b")
