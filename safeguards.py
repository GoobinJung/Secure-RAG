import re
import unicodedata


INJECTION_PATTERNS = (
    ("instruction_override", re.compile(
        r"\b(?:ignore|disregard)\s+(?:(?:all|the)\s+)?"
        r"(?:previous|prior|earlier)\s+(?:instructions?|rules?)\b"
    )),
    ("role_impersonation", re.compile(r"\b(?:system|developer)\s*(?:message\s*)?:")),
    ("answer_redirection", re.compile(r"\binstead\s+of\s+answering\b")),
)


def inspect_chunk(text):
    normalized = unicodedata.normalize("NFKC", text).casefold()
    normalized = "".join(character for character in normalized
                         if unicodedata.category(character) != "Cf")
    for reason, pattern in INJECTION_PATTERNS:
        if pattern.search(normalized):
            return reason
    return None


def screen_chunks(chunks):
    approved = []
    blocked = []
    for chunk in chunks:
        reason = inspect_chunk(chunk["text"])
        if reason:
            blocked.append({"id": chunk["id"], "source": chunk["source"], "reason": reason})
        else:
            approved.append(chunk)
    return approved, blocked
