from flask import Flask

from rag import ANSWER_MODEL, EMBEDDING_MODEL


app = Flask(__name__)


@app.get("/")
def index():
    return {
        "application": "Secure RAG",
        "server_status": "running",
        "answer_model": ANSWER_MODEL,
        "embedding_model": EMBEDDING_MODEL,
    }


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
