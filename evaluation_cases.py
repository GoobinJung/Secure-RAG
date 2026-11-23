import json
from collections import Counter
from pathlib import Path

from ingest import KNOWN_ROLES, load_chunks


CASES_PATH = Path(__file__).resolve().parent / "evaluation_cases.json"
CATEGORIES = ("normal", "attack", "benign_quote", "access_control", "unanswerable")


def validate_cases(data, chunks):
    if data["schema_version"] != 1:
        raise ValueError("Unsupported evaluation case format")
    if set(data["source_labels"]) != set(chunks):
        raise ValueError("Evaluation source labels must cover the current corpus exactly")
    if not set(data["source_labels"].values()) <= {"benign", "attack"}:
        raise ValueError("Unknown document purpose label")
    if not data["cases"]:
        raise ValueError("The evaluation set must contain cases")
    seen_ids = set()
    for case in data["cases"]:
        case_id = case["id"]
        if not case_id or case_id in seen_ids:
            raise ValueError("Evaluation case IDs must be present and unique")
        seen_ids.add(case_id)
        if case["role"] not in KNOWN_ROLES or case["category"] not in CATEGORIES:
            raise ValueError(f"Unknown role or category in {case_id}")
        if not case["question"].strip() or not case["reference_answer"].strip():
            raise ValueError(f"Missing question or reference answer in {case_id}")
        referenced_ids = set(case["reference_source_ids"] + case["forbidden_source_ids"])
        if not referenced_ids <= set(chunks):
            raise ValueError(f"Unknown source ID in {case_id}")
        for source_id in case["reference_source_ids"]:
            if case["role"] not in chunks[source_id]["roles"]:
                raise ValueError(f"Reference answer uses a restricted source in {case_id}")
        for source_id in case["forbidden_source_ids"]:
            if case["role"] in chunks[source_id]["roles"]:
                raise ValueError(f"Forbidden source is authorized for the role in {case_id}")
        attack = case["attack"]
        if case["category"] == "attack":
            if not attack or data["source_labels"].get(attack["source_id"]) != "attack":
                raise ValueError(f"Missing attack source in {case_id}")
            if attack["source_id"] not in case["reference_source_ids"]:
                raise ValueError(f"Attack source is absent from reference sources in {case_id}")
            if not attack["marker"] or attack["marker"] not in chunks[attack["source_id"]]["text"]:
                raise ValueError(f"Attack marker does not match the document in {case_id}")
        elif attack is not None:
            raise ValueError(f"Unexpected attack metadata in {case_id}")


def load_evaluation_cases(path=CASES_PATH):
    data = json.loads(path.read_text(encoding="utf-8"))
    chunks = {chunk["id"]: chunk for chunk in load_chunks()}
    validate_cases(data, chunks)
    return data


def main():
    data = load_evaluation_cases()
    counts = Counter(case["category"] for case in data["cases"])
    print(f"Evaluation cases: {len(data['cases'])}")
    for category in CATEGORIES:
        print(f"  {category}: {counts[category]}")
    labels = Counter(data["source_labels"].values())
    print(f"Corpus labels: {labels['benign']} benign chunks, {labels['attack']} attack chunks")
    print("Case definitions and source references are valid.")
    print("Model evaluation will use these questions and reference answers.")


if __name__ == "__main__":
    main()
