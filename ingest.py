import json
import re
from pathlib import Path


CORPUS_DIR = Path(__file__).resolve().parent / "corpus"
KNOWN_ROLES = {"employee", "admin"}
POLICY_HEADING = re.compile(r"^##[ \t]+(.+?)\s*$", re.MULTILINE)


def policy_sections(text):
    headings = list(POLICY_HEADING.finditer(text))
    boundaries = [heading.start() for heading in headings[1:]] + [len(text)]
    for heading, end in zip(headings, boundaries):
        yield heading.group(1), text[heading.end():end].strip()


def faq_entries(text):
    for entry in json.loads(text):
        yield entry["question"], entry["answer"]


def incident_entries(text):
    for line in text.splitlines():
        if line.strip():
            entry = json.loads(line)
            yield entry["title"], f"{entry['timestamp']}\n{entry['note']}"


SEGMENTERS = {
    "policy": policy_sections,
    "faq": faq_entries,
    "incident_notes": incident_entries,
}


def load_chunks(corpus_dir=CORPUS_DIR):
    manifest = json.loads((corpus_dir / "manifest.json").read_text(encoding="utf-8"))
    for document in manifest:
        roles = document["roles"]
        if not roles or not set(roles) <= KNOWN_ROLES:
            raise ValueError(f"Invalid access roles for {document['id']}")

        path = corpus_dir / document["file"]
        style = document["style"]
        segments = list(SEGMENTERS[style](path.read_text(encoding="utf-8")))
        if not segments or any(not body.strip() for _, body in segments):
            raise ValueError(f"Missing segment content in {document['file']}")

        for position, (heading, body) in enumerate(segments, start=1):
            yield {
                "id": f"{document['id']}:{position}",
                "document_id": document["id"],
                "title": document["title"],
                "style": style,
                "source": f"corpus/{document['file']}",
                "heading": heading,
                "roles": roles.copy(),
                "text": f"{document['title']}\n{heading}\n{body}",
            }


if __name__ == "__main__":
    for chunk in load_chunks():
        print(json.dumps(chunk))
