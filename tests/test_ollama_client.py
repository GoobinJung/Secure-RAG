import io
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from ollama_client import request_ollama


class OllamaClientTests(unittest.TestCase):
    def test_metadata_request_uses_get(self):
        with patch("ollama_client.build_opener") as build:
            build.return_value.open.return_value.__enter__.return_value = io.BytesIO(b'{"models": []}')
            self.assertEqual(request_ollama("tags"), {"models": []})
        request = build.return_value.open.call_args.args[0]
        self.assertEqual(request.get_method(), "GET")
        self.assertIsNone(request.data)

    def test_model_request_still_uses_post(self):
        with patch("ollama_client.build_opener") as build:
            build.return_value.open.return_value.__enter__.return_value = io.BytesIO(b'{"done": true}')
            request_ollama("chat", {"model": "llama3.2:3b"})
        request = build.return_value.open.call_args.args[0]
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(json.loads(request.data)["model"], "llama3.2:3b")

    def test_get_failure_has_a_readable_error(self):
        with patch("ollama_client.build_opener") as build:
            build.return_value.open.side_effect = HTTPError("http://127.0.0.1", 503, "Unavailable", {}, None)
            with self.assertRaisesRegex(RuntimeError, "HTTP 503"):
                request_ollama("tags")
