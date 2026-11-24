
import secrets
from datetime import timedelta

from flask import Flask, abort, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from rag import ANSWER_MODEL, EMBEDDING_MODEL, answer_question


app = Flask(__name__)
app.config.update(
    SECRET_KEY=secrets.token_hex(32),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_REFRESH_EACH_REQUEST=False,
    PERMANENT_SESSION_LIFETIME=timedelta(minutes=30),
    MAX_CONTENT_LENGTH=64 * 1024,
)

# Public, fictional accounts for the loopback-only class demonstration.
DEMO_USERS = {
    "employee": {"role": "employee", "password_hash": generate_password_hash("employee-demo")},
    "admin": {"role": "admin", "password_hash": generate_password_hash("admin-demo")},
}


@app.before_request
def load_account():
    username = session.get("username")
    user = DEMO_USERS.get(username)
    g.account = None
    if user is not None:
        g.account = {"username": username, "role": user["role"]}


@app.before_request
def check_form_token():
    if request.method == "POST":
        expected = session.get("csrf_token")
        supplied = request.form.get("csrf_token", "")
        if not expected or not secrets.compare_digest(expected.encode("utf-8"), supplied.encode("utf-8")):
            abort(400, description="The form expired. Reload the page and try again.")


def csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return session["csrf_token"]


@app.context_processor
def template_context():
    return {"account": g.account, "csrf_token": csrf_token}


@app.after_request
def response_headers(response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
    )
    return response


@app.errorhandler(400)
def invalid_request(error):
    if request.endpoint == "chat":
        return {"error": "Your session changed or the form expired. Return to the app.", "reset_chat": True}, 400
    return render_template(
        "error.html", heading="Please reload the form",
        message="The form expired or the request was invalid. Return to the app and try again. You may need to sign in again.",
    ), 400


@app.errorhandler(413)
def request_too_large(error):
    if request.endpoint == "chat":
        return {"error": "Request too large. Use a question of up to 2,000 characters."}, 413
    return render_template(
        "error.html", heading="Request too large",
        message="This request exceeds the size limit. Return to the app and enter a question of up to 2,000 characters.",
    ), 413


def process_question():
    question = request.form.get("question", "").strip()
    defense = request.form.get("defense", "guarded")
    result = None
    error = None
    status_code = 200
    if defense not in ("baseline", "guarded"):
        error = "Choose Baseline or Guarded mode."
        defense = "guarded"
        status_code = 400
    elif not question or len(question) > 2000:
        error = "Enter a question between 1 and 2,000 characters."
        status_code = 400
    else:
        try:
            result = answer_question(question, g.account["role"], defense=defense)
        except (RuntimeError, ValueError) as model_error:
            error = str(model_error)
            status_code = 502
    return question, defense, result, error, status_code


@app.route("/", methods=["GET", "POST"])
def index():
    if g.account is None:
        return redirect(url_for("login"))
    question, defense, result, error, status_code = "", "guarded", None, None, 200
    if request.method == "POST":
        question, defense, result, error, status_code = process_question()
    return render_template(
        "index.html", answer_model=ANSWER_MODEL, embedding_model=EMBEDDING_MODEL,
        question=question, defense=defense, result=result, error=error,
    ), status_code


@app.post("/chat")
def chat():
    if g.account is None:
        return {"error": "Please sign in again.", "reset_chat": True}, 401
    question, defense, result, error, status_code = process_question()
    if status_code == 400:
        return {"error": error}, status_code
    return {
        "html": render_template("_exchange.html", question=question, defense=defense, result=result, error=error),
        "context": session["csrf_token"],
        "ok": status_code == 200,
    }, status_code


@app.get("/chat/session")
def chat_session():
    if g.account is None:
        return {"context": None}, 401
    return {"context": csrf_token()}


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = DEMO_USERS.get(username)
        if user is None or not check_password_hash(user["password_hash"], password):
            return render_template("login.html", error="Incorrect username or password."), 401
        session.clear()
        session["username"] = username
        session.permanent = True
        csrf_token()
        return redirect(url_for("index"))
    if g.account is not None:
        return redirect(url_for("index"))
    return render_template("login.html", error=None)


@app.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.get("/health")
def health():
    return {
        "application": "Secure RAG",
        "server_status": "running",
        "answer_model": ANSWER_MODEL,
        "embedding_model": EMBEDDING_MODEL,
    }


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
