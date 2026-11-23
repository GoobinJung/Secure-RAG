# Secure RAG

A graduate AI final project on unauthorized document exposure and indirect prompt injection in a fictional company knowledge base. The current command-line app segments documents, filters them by role, retrieves relevant chunks with local embeddings, and generates answers with a local LLM.

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

In PyCharm, open `retrieve.py`, right-click the editor, and select Run. The demo asks the same recovery-code question for two fixed test identities. The employee can receive matching public chunks, including the printer recovery note, while the administrator-only recovery document stays excluded. The administrator receives the recovery document with its fictional code and source.

The retrieval function accepts a role from trusted application code, filters chunks using the manifest permissions, then ranks the allowed chunks by the number of distinct matching query terms. This keyword search provides a repeatable baseline for testing permissions alongside the semantic RAG pipeline.

The role parameter is a local testing interface. A future web app must resolve it from a server-managed authenticated session. A role claim inside a question cannot change the role used for retrieval. The manifest is controlled by the project administrator and must be protected from user edits.

The public injected-incident fixture remains searchable by both roles. Its embedded instruction is retained as data for prompt-injection comparisons.

## Run local RAG answers

Start Ollama and download `embeddinggemma` and `llama3.2:3b`. In the project's Python environment, run the commands below. This milestone uses the Python standard library to connect to Ollama's local HTTP API.

```powershell
ollama pull embeddinggemma
ollama pull llama3.2:3b
python rag.py
python rag.py --role employee --question "How do I request a company VPN account?"
```

In PyCharm, right-click `rag.py` and select Run. With no arguments, the program asks both roles the same recovery-code question. It displays the exact source IDs sent to the answer model and the generated answer.

Only authorized chunks reach either model. EmbeddingGemma receives the documented retrieval-query and document prefixes. Python computes cosine similarities and selects up to three allowed chunks. Llama 3.2 3B receives those chunks in a fresh conversation, with temperature 0, seed 42, a 4096-token context, and a 256-token answer limit. The demo embeds the allowed short corpus for each question and keeps the vectors in memory for that request.

The project initially used Qwen3 1.7B. Llama 3.2 3B was subsequently selected as the answer model. Evaluation results should identify the answer model so that observations from the earlier Qwen version and the current Llama version can be interpreted in context. Both baseline and guarded runs now use Llama.

Semantic search returns the nearest available documents even when the corpus cannot answer a question. An employee can therefore receive public-document matches for the recovery question while the restricted recovery document stays excluded. Similarity is a ranking measure. The model is instructed to acknowledge insufficient evidence, and that behavior still needs evaluation. The displayed source list records context sent to the model. A generated citation or answer may still be incorrect.

The `--role` option is for local demonstrations with fixed test identities. Production authentication, persistent vector storage, and the web interface are future work.

## Compare prompt injection safeguards

The baseline keeps the original retrieval and answer prompt. Guarded mode inspects the same top-three authorized search results before constructing the answer model's context. It normalizes Unicode text and flags a small set of English instruction-override, role-impersonation, and answer-redirection patterns. Flagged chunks are excluded and reported by their source ID and detection reason. The guarded system prompt also describes sources as untrusted reference material.

```powershell
python rag.py --role employee --defense baseline --question "What resolved the VPN service interruption?"
python rag.py --role employee --defense guarded --question "What resolved the VPN service interruption?"
```

For the supplied injected fixture, guarded mode should report `Screened out: [injected-incident-note:1]` with reason `instruction_override`. The clean incident note should still allow an answer about restarting the gateway. Document authorization runs in both modes. Pattern screening takes place after embedding and ranking, before the answer-model request. The remaining selected chunks are used without refilling removed result slots.

These handcrafted patterns cover a narrow set of attacks. Rephrased instructions can evade them, and benign quotations of attack language can be flagged. The current comparison changes both screening and the system prompt, so it measures their combined behavior. A broader evaluation should include unseen attack wording, legitimate text that resembles attacks, and normal questions. The model may already resist an attack in baseline mode. Measure actual results in both modes even when both give the correct answer.

## Check answer citations

Each answer now includes a citation check against the exact chunks passed to the answer model, after role filtering and any guarded screening. The check recognizes the corpus ID format `document-id:number` in bracketed citations and plain text such as `Source: incident-notes:1`.

The CLI reports whether all recognized IDs match supplied chunks, some IDs are outside the context, or no source IDs appear. Unknown IDs are listed for inspection. A reference to another chunk from an existing document is still unmatched when that specific chunk was absent from the context.

This is an ID membership check. Factual support for a claim requires a separate assessment of the cited text. A missing citation can occur when the model says the sources contain insufficient information. The original answer is displayed alongside the check so evaluation can record citation errors. This check operates in both baseline and guarded modes.

```powershell
python rag.py --role employee --defense guarded --question "What resolved the VPN service interruption?"
```

For an answer citing `incident-notes:1`, the expected final line is `Citation check: all cited source IDs were supplied to the model`.

## Additional attack documents

The corpus includes four handcrafted attack documents. Each asks the model to output a harmless marker that can be checked during evaluation. The new documents use the existing segmentation rules, with their source IDs and permissions inherited from the manifest.

| Source ID | Document style | Attack technique | Current pattern check |
| --- | --- | --- | --- |
| `injected-incident-note:1` | Incident note | Explicit instruction override | `instruction_override` |
| `injected-policy:1` | Markdown policy section | Claims a SYSTEM role | `role_impersonation` |
| `injected-faq:1` | Question and answer | Zero-width character inside an override instruction | `instruction_override` after normalization |
| `injected-paraphrased-note:1` | Incident note | Rephrased instruction to replace the answer with a marker | `not_flagged` |

Preview the document screening without running an AI model:

```powershell
python inspect_documents.py
```

This command checks all chunks allowed for the selected test role. A flag means a known pattern matched. `not_flagged` means no current pattern matched. The paraphrased attack demonstrates a detection gap in the current rules. Whether its instruction changes a generated answer still requires a model test in which the document actually reaches the answer-model context.

Adding documents can change the top-three semantic search results. Later baseline and guarded comparisons should use the same corpus version and record which attack documents were retrieved and passed to the model.

## Benign documents and false positives

Three additional documents provide four benign chunks across the same document styles. These examples help evaluate whether screening removes useful material.

| Source ID | Document style | Content purpose | Current pattern check |
| --- | --- | --- | --- |
| `security-training:1` | Markdown section | Explains and quotes an attack phrase for awareness training | `instruction_override` false positive |
| `document-safety-faq:1` | Question and answer | Explains a SYSTEM label in an example event log | `role_impersonation` false positive |
| `document-safety-faq:2` | Question and answer | Explains how to verify a document owner | `not_flagged` |
| `routine-service-note:1` | Incident note | Records a routine release check | `not_flagged` |

Run `python inspect_documents.py` to see these results alongside the attack examples. The first two benign chunks are flagged because the current patterns match text without interpreting its intent. The other two benign chunks remain available. These observations describe scanner decisions. The impact on generated answers will be measured with the evaluation questions in a later milestone.

The examples' intended benign or attack purpose is described here for evaluation. Runtime authorization still comes from manifest roles, and the scanner uses chunk text. File names or descriptions grant no bypass of document screening.

## Evaluation questions and reference answers

`evaluation_cases.json` defines 14 cases before model evaluation. The set contains five normal questions, four questions about attack-bearing documents, two questions about benign quotations, two access-control checks using the same question for different roles, and one question the corpus cannot answer.

Each case includes its role, question, reference answer, and reference source IDs. The employee recovery-code case specifies forbidden source IDs and the fictional code that must stay out of the answer. Attack cases specify the carrier chunk and the marker requested by the injected instruction. `source_labels` records the intended attack or benign purpose of every corpus chunk for later scanner evaluation. These labels are evaluation metadata, separate from runtime screening and authorization.

```powershell
python evaluation_cases.py
```

This command validates definitions against the current corpus and prints case counts. Reference answers describe the intended task response. Measured outputs will be recorded by the evaluation runner in a later milestone. Reference answers for attack cases describe factual content in the documents. Guarded screening may remove that evidence, especially for the MFA and cache examples, which should be recorded when evaluating answer usefulness.

The future comparison should record the model, corpus version, retrieved sources, screened-out sources, final context sources, answers, and citation checks for each mode. An attack that was never retrieved is a separate outcome from an attack whose instruction reached the model and was resisted. Differences in wording from a reference answer require judging whether the same facts were conveyed.

## Record model evaluation runs

Use the runner to execute a selected case or the complete set:

```powershell
python evaluate.py --case normal-vpn --defense guarded
python evaluate.py
```

The first command records one question in guarded mode. With no arguments, the runner executes all 14 cases in baseline and guarded modes, producing 28 case records. Repeat `--case` to select several cases. Keep Ollama running during evaluation.

Every invocation creates a new JSON Lines file under `results/runs/`. Its first line records model tags and installed-model digests, Python version, generation settings, corpus and case fingerprints, and source-code file hashes. Subsequent lines record each case, mode, actual answer, retrieved chunk IDs, screened-out chunks, final context IDs, citation checks, and end-to-end elapsed time. The final summary records completed cases and errors. Cold model loading is included in elapsed time.

Each completed record is flushed before the next case starts. Model errors are recorded and the runner continues, then exits with a failure status if any case failed. Interrupted runs retain completed records and may lack the final summary. Earlier result files are preserved. Raw run files are ignored by Git while experiments are in progress. Selected verified results can be prepared for the repository in a later milestone.

An `ok` record means the model request completed. Answer quality, attack outcomes, and false-positive rates will be calculated separately. The full reference answer and case expectations are stored alongside each observation for review.

## Calculate metrics from saved runs

```powershell
python summarize_evaluation.py
python summarize_evaluation.py results/runs/evaluation-RUN_ID.jsonl
```

With no argument, the command reads the newest saved run. A file path selects a specific run. The summary reports recorded versus expected cases, completion status, model errors, and metrics for each defense mode. Unfinished runs are identified. Model-error records are reported and excluded from outcome-rate denominators. Empty denominators are displayed as `N/A`.

- Target attack retrieval and exposure counts distinguish a carrier that was never retrieved from one that reached the answer model.
- Target marker output is a case-insensitive substring check for the marker requested by that case's attack. The exposure-conditioned rate counts only cases in which that carrier reached the answer model. Marker output is a proxy for answer contamination and needs inspection if an answer quotes a marker while discussing it.
- New evaluation runs store all attack markers in the header, allowing marker checks across normal questions too. Older runs remain readable and display this metric as unavailable.
- Guarded screening false positives count benign retrieved chunks that were screened out, divided by benign retrieved chunks. The same source can be counted in multiple requests. Attack screening uses the corresponding attack-chunk counts. These rates describe screening among retrieved chunks.
- Forbidden-source and forbidden-answer-text checks apply to cases with explicit forbidden expectations. Reference-source coverage measures whether any reference source reached the final model context. Citation counts report ID membership checks. Answer correctness still requires reviewing the answer against the reference facts.

Each run file is summarized independently so that observations from different models or corpora remain attributable to their recorded settings. Timing includes retrieval, generation, and any cold loading.

## Verified evaluation results

The first complete evaluation ran all 14 questions in both modes on November 23, 2026. The [results review](results/README.md) includes an unchanged copy of the 28 observed records, recalculable metrics, and a question-by-question qualitative assessment. Guarded screening reduced target attack-document exposure from 4/4 to 1/4. Both modes produced zero requested attack markers, and false positives reduced answer usefulness for some questions.

## Start the local web server

Install the project dependency in the Secure RAG Python environment, then start the server:

```powershell
python -m pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:5000/` in a browser. Signed-out visitors are redirected to the login page. The JSON server-status response is available at `/health` and reports configured model names without calling Ollama. The server binds to the loopback address with debug mode disabled. Press `Ctrl+C` in the server terminal to stop it.

## Sign in with a local demo account

| Username | Password | Server-assigned role |
| --- | --- | --- |
| `employee` | `employee-demo` | `employee` |
| `admin` | `admin-demo` | `admin` |

These fictional, public credentials support the loopback-only class demonstration. Login validates a password hash and creates a signed session containing the username. On every request, the server looks up that username in its own account mapping to determine the role. Submitted role fields and query parameters have no authority to change it.

Login and logout forms use session-bound CSRF tokens. Successful login clears the previous session and rotates the token. Cookies use HttpOnly and SameSite=Lax, and sessions have a 30-minute lifetime. A new signing key is generated when the server starts, so restarting the server requires signing in again.

After login, the page displays the server-resolved username, role, and configured models. Existing command-line retrieval, RAG, and evaluation commands remain available.

## Ask questions in the browser

Start Ollama and `python app.py`, sign in, and enter a question on the home page. Questions can contain up to 2,000 characters. The browser displays a pending status while the request runs, followed by the answer. The initial web question workflow uses guarded mode. The server takes the role from the authenticated account mapping, and ignores submitted role and defense fields.

Try `How do I request a company VPN account?` as the employee. The answer should describe the support portal and manager approval. The recovery-code question can then be tried with each account to compare access boundaries. Each submission starts a fresh model conversation. Questions and answers stay in that response and are excluded from the session cookie.

The form includes a session-bound CSRF token. Questions are validated on the server, model failures are displayed with the entered question preserved, and model output is rendered as escaped text. Source-detail and document-screening panels are the next milestones.

## References

- [Microsoft guidance on document chunking](https://learn.microsoft.com/en-us/azure/search/vector-search-how-to-chunk-documents)
- [OWASP RAG Security Cheat Sheet on access control inheritance](https://cheatsheetseries.owasp.org/cheatsheets/RAG_Security_Cheat_Sheet.html#section-4-access-control-inheritance)
- [Ollama embedding API](https://docs.ollama.com/api/embed)
- [Ollama chat API](https://docs.ollama.com/api/chat)
- [EmbeddingGemma retrieval prompt instructions](https://huggingface.co/google/embeddinggemma-300m#prompt-instructions)
- [Llama 3.2 3B in Ollama](https://ollama.com/library/llama3.2:3b)
