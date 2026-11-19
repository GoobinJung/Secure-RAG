import json
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener


OLLAMA_URL = "http://127.0.0.1:11434/api/"


def request_ollama(endpoint, payload):
    request = Request(
        OLLAMA_URL + endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    # A local model request should go directly to the loopback address.
    opener = build_opener(ProxyHandler({}))
    try:
        with opener.open(request, timeout=180) as response:
            result = json.load(response)
    except HTTPError as error:
        raise RuntimeError(
            f"Ollama returned HTTP {error.code}. Check 'ollama list' for "
            f"the requested model: {payload['model']}."
        ) from error
    except (URLError, OSError) as error:
        raise RuntimeError(
            "Cannot complete the local Ollama request. Open Ollama, check "
            "'ollama list', and retry. Initial model loading can take longer."
        ) from error
    except ValueError as error:
        raise RuntimeError("Ollama returned an invalid JSON response.") from error
    if not isinstance(result, dict) or result.get("error"):
        raise RuntimeError("Ollama returned an unsuccessful response.")
    return result
