import argparse

from ingest import KNOWN_ROLES
from retrieve import authorized_chunks
from safeguards import inspect_chunk


def main():
    parser = argparse.ArgumentParser(description="Preview screening of chunks allowed for a test role.")
    parser.add_argument("--role", choices=sorted(KNOWN_ROLES), default="employee")
    args = parser.parse_args()
    chunks = authorized_chunks(args.role)
    print(f"Role: {args.role} | Authorized chunks: {len(chunks)}")
    print("Current pattern-screening results:")
    for chunk in chunks:
        reason = inspect_chunk(chunk["text"])
        print(f"  {chunk['id']} | {reason or 'not_flagged'}")
    print("\nnot_flagged means the current patterns did not match this chunk.")


if __name__ == "__main__":
    main()
