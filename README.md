# Secure RAG

A graduate AI final project on unauthorized document exposure and indirect prompt injection in a fictional company knowledge base. The current milestone segments documents and applies role permissions before ranking search results.

## Document segmentation

Segmentation (or chunking) determines which part of a document is stored as one retrievable record. The source title, local source path, chunk ID, document style, and allowed roles travel with each chunk.

| Document style | Segmentation pattern | Why this boundary |
| --- | --- | --- |
| Policy or procedure (Markdown) | One chunk per `##` section, including the section heading and its body | Keeps each policy rule next to its exceptions, and keeps the steps of a short procedure together. |
| FAQ (JSON) | One chunk per question and its full answer | The question can match a query and the answer stays in the same retrieval result. |
| Incident notes (JSON Lines) | One chunk per incident record, including its title, timestamp, and note | Keeps separate incidents from getting combined and preserves time context for each entry. |

These patterns target the short, structured demonstration documents. For larger policy sections, a later extension could split at paragraph boundaries and repeat the section heading. Each document inherits its permissions from the project-controlled corpus manifest. The text being indexed has no authority to change those permissions.

## Preview the chunk records

From this folder, use Python 3.10 or newer. The ingestion milestone uses only the Python standard library.

```powershell
python ingest.py
python -m unittest discover -s tests -v
```

The preview prints one JSON record per chunk. It is intended for local testing and includes the fictional text of restricted fixtures.

## Run the retrieval permissions demo

```powershell
python retrieve.py
```

In PyCharm, open `retrieve.py`, right-click the editor, and select Run. The demo asks the same recovery-code question for two fixed test identities. The employee receives zero matching chunks. The administrator receives the recovery document with its fictional code and source.

The retrieval function accepts a role from trusted application code, filters chunks using the manifest permissions, then ranks the allowed chunks by the number of distinct matching query terms. This keyword search provides a repeatable baseline for testing permissions. Semantic embeddings and LLM answers are planned for the next milestone.

The role parameter is a local testing interface. A future web app must resolve it from a server-managed authenticated session. A role claim inside a question cannot change the role used for retrieval. The manifest is controlled by the project administrator and must be protected from user edits.

The public injected-incident fixture remains searchable by both roles. Its embedded instruction is retained as data for later prompt-injection experiments. This milestone tests document authorization. Prompt-injection defenses and generated answers will be evaluated in later milestones.

## References

- [Microsoft guidance on document chunking](https://learn.microsoft.com/en-us/azure/search/vector-search-how-to-chunk-documents)
- [OWASP RAG Security Cheat Sheet on access control inheritance](https://cheatsheetseries.owasp.org/cheatsheets/RAG_Security_Cheat_Sheet.html#section-4-access-control-inheritance)
