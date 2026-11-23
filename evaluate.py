import argparse
import hashlib
import json
import platform
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from evaluation_cases import load_evaluation_cases
from ingest import load_chunks
from ollama_client import request_ollama
from rag import ANSWER_MODEL, EMBEDDING_MODEL, GENERATION_OPTIONS, answer_question


PROJECT_DIR = Path(__file__).resolve().parent
RUNS_DIR = PROJECT_DIR / "results" / "runs"


def json_fingerprint(value):
    serialized = json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def run_metadata(data, cases, modes):
    models = request_ollama("tags").get("models", [])
    model_digests = {}
    for name in (ANSWER_MODEL, EMBEDDING_MODEL):
        tag = name if ":" in name else name + ":latest"
        matches = [model for model in models if model.get("name") in (name, tag)]
        if len(matches) != 1 or not matches[0].get("digest"):
            raise RuntimeError(f"Cannot identify model {name}. Check 'ollama list'.")
        model_digests[name] = matches[0]["digest"]
    chunks = sorted(load_chunks(), key=lambda chunk: chunk["id"])
    return {
        "type": "run",
        "schema_version": 1,
        "run_id": uuid.uuid4().hex,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "answer_model": ANSWER_MODEL,
        "embedding_model": EMBEDDING_MODEL,
        "model_digests": model_digests,
        "python_version": platform.python_version(),
        "generation_options": GENERATION_OPTIONS.copy(),
        "corpus_sha256": json_fingerprint(chunks),
        "case_definitions_sha256": json_fingerprint(data),
        "code_sha256": {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(PROJECT_DIR.glob("*.py"))
        },
        "source_labels": data["source_labels"],
        "attack_markers": {
            case["attack"]["source_id"]: case["attack"]["marker"]
            for case in data["cases"] if case["attack"] is not None
        },
        "selected_case_ids": [case["id"] for case in cases],
        "defense_modes": modes,
        "expected_records": len(cases) * len(modes),
    }


def record_case(case, mode):
    started = time.perf_counter()
    record = {
        "type": "case",
        "case": case,
        "defense": mode,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        result = answer_question(case["question"], case["role"], defense=mode)
        record.update({
            "status": "ok",
            "answer": result["answer"],
            "answer_generated": bool(result["chunks"]),
            "retrieved_ids": [chunk["id"] for chunk in result["retrieved_chunks"]],
            "context_ids": [chunk["id"] for chunk in result["chunks"]],
            "blocked": result["blocked"],
            "citations": result["citations"],
        })
    except (RuntimeError, ValueError) as error:
        record.update({"status": "error", "error": str(error)})
    record["elapsed_seconds"] = round(time.perf_counter() - started, 3)
    return record


def run_evaluation(data, cases, modes, output_dir=RUNS_DIR):
    metadata = run_metadata(data, cases, modes)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"evaluation-{metadata['run_id']}.jsonl"
    errors = 0
    completed = 0
    print(f"Answer model: {ANSWER_MODEL}", flush=True)
    print(f"Saving results to: {output_path}", flush=True)
    # Exclusive creation preserves earlier runs. Each completed record is flushed.
    with output_path.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(metadata, ensure_ascii=False, allow_nan=False) + "\n")
        handle.flush()
        for case in cases:
            for mode in modes:
                print(f"Running {case['id']} | {mode} ...", flush=True)
                record = record_case(case, mode)
                handle.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
                handle.flush()
                completed += 1
                if record["status"] == "error":
                    errors += 1
                    print(f"  error: {record['error']}", flush=True)
                else:
                    print(f"  ok | {record['elapsed_seconds']:.3f} seconds", flush=True)
        summary = {"type": "summary", "completed_records": completed, "errors": errors}
        handle.write(json.dumps(summary) + "\n")
        handle.flush()
    print(f"Completed records: {completed} | Errors: {errors}", flush=True)
    return output_path, summary


def main():
    parser = argparse.ArgumentParser(description="Run predefined RAG questions and save observed outputs.")
    parser.add_argument("--case", action="append", dest="case_ids", help="Run one case ID. Repeat to select more.")
    parser.add_argument("--defense", choices=("baseline", "guarded", "both"), default="both")
    args = parser.parse_args()
    try:
        data = load_evaluation_cases()
        selected_ids = set(args.case_ids or [case["id"] for case in data["cases"]])
        known_ids = {case["id"] for case in data["cases"]}
        if selected_ids - known_ids:
            parser.error("Unknown case IDs: " + ", ".join(sorted(selected_ids - known_ids)))
        cases = [case for case in data["cases"] if case["id"] in selected_ids]
        modes = ["baseline", "guarded"] if args.defense == "both" else [args.defense]
        _, summary = run_evaluation(data, cases, modes)
    except (RuntimeError, ValueError, OSError) as error:
        parser.exit(1, f"Error: {error}\n")
    if summary["errors"]:
        parser.exit(1, "Evaluation finished with errors. Inspect the saved records before summarizing.\n")


if __name__ == "__main__":
    main()
