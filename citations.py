import re


SOURCE_ID = re.compile(r"(?<![\w-])[A-Za-z][A-Za-z0-9_-]*:[0-9]+(?![\w-])")


def check_citations(answer, chunks):
    """Compare source IDs in an answer with the exact context given to the LLM."""
    cited_ids = sorted(set(SOURCE_ID.findall(answer)))
    supplied_ids = {chunk["id"] for chunk in chunks}
    unknown_ids = sorted(set(cited_ids) - supplied_ids)
    if not cited_ids:
        status = "missing"
    elif unknown_ids:
        status = "unmatched"
    else:
        status = "matched"
    return {"status": status, "cited_ids": cited_ids, "unknown_ids": unknown_ids}
