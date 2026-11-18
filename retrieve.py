import re

from ingest import KNOWN_ROLES, load_chunks


STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "can", "do", "for",
    "from", "how", "i", "in", "is", "it", "of", "on", "or", "the", "to",
    "was", "what", "when", "where", "which", "who", "with",
}


def search_terms(text):
    return set(re.findall(r"[a-z0-9]+", text.lower())) - STOP_WORDS


def authorized_chunks(role):
    """Resolve document permissions before any ranking or model request."""
    if role not in KNOWN_ROLES:
        raise ValueError("Unknown user role")
    return [chunk for chunk in load_chunks() if role in chunk.get("roles", [])]


def retrieve(query, role, limit=3):
    """Return matching chunks authorized for a role supplied by trusted app code."""
    chunks = authorized_chunks(role)
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
        raise ValueError("Search limit must be a positive integer")

    terms = search_terms(query)
    if not terms:
        return []

    matches = []
    for chunk in chunks:
        score = len(terms & search_terms(chunk["text"]))
        if score:
            matches.append((score, chunk))

    matches.sort(key=lambda match: (-match[0], match[1]["id"]))
    return [chunk for _, chunk in matches[:limit]]


def main():
    query = "What is the administrator emergency recovery code?"
    print(f"Question: {query}")
    # These fixed roles are test identities for the local retrieval demo.
    for role in ("employee", "admin"):
        results = retrieve(query, role)
        print(f"\nRole: {role} | Returned chunks: {len(results)}")
        if not results:
            print("No matching documents available for this user.")
        for chunk in results:
            print(f"Source: {chunk['source']} | Chunk: {chunk['id']}")
            print(chunk["text"])


if __name__ == "__main__":
    main()
