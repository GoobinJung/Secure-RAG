# Securing a RAG Application

Goobin Jung  
Oklahoma Christian University  
Graduate Artificial Intelligence Final Project  
November 24, 2026

## What I built and why

I built Secure RAG, a local application that answers questions using fictional company documents. RAG stands for retrieval augmented generation. The application retrieves relevant document excerpts and gives them to a language model as evidence for its answer. Employees and administrators sign in through a browser, ask questions, and inspect the sources used by the model.

I chose this topic because it connects AI with my cybersecurity studies. A document assistant has to do more than give a useful answer. It also has to respect document permissions and handle instructions that an attacker may place inside a document. My main questions were whether an employee could receive administrator-only information and whether document instructions could redirect the model's answer.

The project uses pretrained embedding and language models as part of a working system. I developed document segmentation, role-based retrieval, two defense modes, citation checks, a web application, and an evaluation workflow. The evaluation found that Guarded mode reduced exposure to the supplied attack documents, but also removed useful material. Both modes produced zero requested attack markers, so the results do not show an improvement in marker-based attack success.

## System design and document segmentation

The fictional Northbridge knowledge base contains 11 documents that produce 16 chunks. Twelve chunks are labeled benign and four contain test attacks. Employees can access 14 chunks. Administrators can access all 16, including a recovery procedure with a fictional demonstration code. The attack and benign labels are used for evaluation, not as shortcuts for runtime detection.

I used a different segmentation pattern for each document style, following Professor Griffin's request to explain the storage patterns.

| Document style | Segmentation pattern | Why I used it |
| --- | --- | --- |
| Markdown policy or procedure | One chunk for each `##` section, including its heading and body | A short rule stays with its exceptions, and a procedure's steps remain together. |
| JSON FAQ | One question and its complete answer per chunk | The retriever can match the question while retaining the answer in the same record. |
| JSON Lines incident notes | One incident record per chunk, including title, timestamp, and note | Separate incidents stay separate and keep their time context. |

Every chunk carries its document title, source path, ID, style, and permitted roles. Its text includes the document title and section or record heading. There is no sliding-window overlap. The documents are short enough to keep these meaningful units intact. Microsoft describes structure-based splitting as one option for document chunking; here, the boundaries are implemented directly for these three file formats. [Microsoft chunking guidance](https://learn.microsoft.com/en-us/azure/search/vector-search-how-to-chunk-documents)

Storage is deliberately small in scope. Source files and a trusted permissions manifest stay on disk. For each question, the application rebuilds the chunks and keeps the embeddings in memory for that request. There is no persistent vector database. These chunks are the logical storage and retrieval units. For a larger policy section, I would add a token limit and paragraph-based splitting while repeating the heading and permissions on every resulting chunk.

After sign-in, the server resolves the role from its account mapping. It filters the chunks before sending text to either the embedding model or the answer model. A role written inside a question or submitted as an extra form field has no authority to promote an employee. This follows OWASP's guidance to carry permissions to chunks and enforce access before content reaches the model. [OWASP RAG security guidance](https://cheatsheetseries.owasp.org/cheatsheets/RAG_Security_Cheat_Sheet.html#section-4-access-control-inheritance)

The embedding model encodes the question and allowed chunks. The application normalizes the vectors, calculates cosine similarity, and selects up to three results. Baseline mode sends those authorized results with the original source-grounding prompt. Guarded mode first normalizes Unicode and removes chunks matching instruction-override, role-impersonation, or answer-redirection patterns. It also adds a prompt describing sources as untrusted evidence. Removed slots are not refilled. If no chunks remain, the application returns an abstention without calling the answer model.

The browser uses a dark chat interface with questions and replies shown in sequence. Each reply records its defense mode. Security checks and source excerpts are collapsed until the user expands them, keeping the answer easy to read. Citation validation compares recognized IDs with the IDs supplied to the model. This checks membership, not whether a source proves a claim. Questions, source text, and answers are escaped when rendered in HTML.

For readability, the browser turns supplied source IDs into small references such as [1]. Selecting a reference opens its matching source in the same reply. The original chunk ID stays in the source details. Unknown IDs are marked unverified and are not linked. This formatting is separate from the raw model answer, which retains its original IDs for citation validation and evaluation.

The conversation stays in the current page rather than in browser storage or the session cookie. Each question is searched independently, so earlier replies are not passed back to the model. New chat clears the display. Reloading or leaving the page also clears it, and session checks and cross-tab notifications clear a chat when a changed login is detected. Responses from an outdated login context are discarded. This limits accidental carryover of an administrator's displayed answers into another account's chat.

## Technology choices and alternatives

I used Python because the ingestion, retrieval, evaluation, and web components could share the same data structures. Flask provided routes, templates, and session handling for the employee/admin workflow. It let me make role resolution and form validation explicit. A framework such as Streamlit would be another way to build a demo interface, but the Flask routes fit this application's account and request handling. PyCharm was the development environment, and GitHub recorded progress in separate commits. [Flask documentation](https://flask.palletsprojects.com/en/stable/)

Ollama runs both models locally through HTTP. This application uses its embedding endpoint to obtain vectors and its chat endpoint to generate answers. The Python connection uses the standard library. Local execution avoids a paid inference API and keeps these document requests on loopback. A hosted service would be another deployment option, with different cost and data-handling decisions. Local execution still requires model downloads and enough resources on the machine. [Ollama embedding API](https://docs.ollama.com/api/embed), [Ollama chat API](https://docs.ollama.com/api/chat)

EmbeddingGemma supplies semantic search vectors. The application uses Google's documented retrieval prefixes for queries and documents. This allows a question to be compared with relevant text even when wording differs. The project also includes a simple keyword retriever as an inspectable permissions test. Its results are not the Baseline mode used in the security evaluation; both evaluated modes use semantic retrieval. [EmbeddingGemma prompt instructions](https://huggingface.co/google/embeddinggemma-300m#prompt-instructions)

The answer model is Llama 3.2 3B, a small model that ran on my development machine through Ollama. The project initially used Qwen3 1.7B and later switched to Llama. I did not run a controlled quality comparison between them, so I cannot claim that Llama was more accurate or more secure. The complete recorded evaluation identifies the Llama model and installed-model digests. [Llama model listing](https://ollama.com/library/llama3.2:3b)

I used in-memory cosine search rather than adding a vector database or a larger RAG framework. With 16 chunks, this keeps authorization, ranking, and context construction visible in the code. It also means the corpus is embedded again for each request. A database would become more useful at a larger scale, but its permission filters and updates would need their own tests.

## Development and difficulties

Development began with document segmentation and access metadata. The next stages added keyword permission checks, local semantic retrieval, and generated answers. Later commits added screening, citation validation, attack fixtures, benign quotations, predefined questions, run recording, and metric summaries. The browser application was built after the command-line pipeline and complete evaluation were working. Login, question submission, source inspection, mode comparison, and error recovery were added separately. I then changed the form-based layout to a chat interface with a dark theme and collapsible inspection panels.

The main difficulties for me were prompt injection and normal documents being incorrectly blocked. An indirect injection is difficult because it enters through material the system retrieves as evidence. The attack fixtures tried direct instruction overrides, a claimed system role, a hidden Unicode character inside an instruction, and a paraphrased redirection. The expected attack outputs were harmless marker strings that could be checked in the saved answers.

Unicode normalization helped expose the instruction with an invisible character. Pattern checks identified the direct override and role-label examples, but the paraphrased attack did not match. That gap remains unresolved in the current rules. The model did not output its marker in the saved evaluation, but that observation does not mean the scanner detected it.

False positives showed another problem. A security-training document quoted an override instruction as an example, and a FAQ explained a `SYSTEM:` label in an ordinary log. The scanner matched those strings without understanding their educational purpose. I added benign cases and measured the exclusions instead of treating every flag as a successful defense. The current rules still have this limitation. Removing a whole chunk can also discard useful facts together with an attack, as happened with the MFA instructions.

There were setup problems as well. Git authentication through the terminal failed, and pushing through PyCharm's GitHub integration worked. A run configuration initially used the drawing-recognition project's Python environment. Selecting Secure RAG's own virtual environment corrected that configuration. These issues reinforced the need to check the actual environment used by a run configuration.

## Evaluation and observed results

The November 23, 2026 experiment used 14 predefined questions in Baseline and Guarded modes, producing 28 completed records with no request errors. The cases included five normal tasks, four attack-bearing documents, two benign quotations, employee/admin recovery checks, and one question without an answer in the corpus. There was one run per question and mode.

The JSONL record stores the model digests, generation options, corpus and question fingerprints, code hashes, retrieved IDs, blocked chunks, final context, answer, citations, errors, and time. Generation used temperature 0, seed 42, a 4096-token context, and a 256-token output limit. The raw observations are preserved in the repository with the [full results review](results/README.md) and can be summarized again without calling a model.

| Observation | Baseline | Guarded |
| --- | --- | --- |
| Target attack document retrieved | 4/4 | 4/4 |
| Target attack document sent to answer model | 4/4 | 1/4 |
| Requested target marker output | 0/4 | 0/4 |
| Any known attack marker in answers | 0/14 | 0/14 |
| Reference source in final context | 12/12 | 9/12 |
| Employee case with forbidden context | 0/1 | 0/1 |
| Employee case with forbidden answer text | 0/1 | 0/1 |
| Citation IDs matched / unmatched / missing | 10 / 0 / 4 | 8 / 0 / 6 |
| Tasks met in qualitative review | 12/14 | 10/14 |

Guarded removed 9 of 11 retrieved attack-chunk occurrences, or 81.8%. It also removed 5 of 31 benign-chunk occurrences, or 16.1%. Occurrences include the same chunk retrieved in different questions. The targeted attack document reached the model in one of four Guarded attack cases, compared with all four Baseline cases.

After the run, each answer was reviewed against the expected facts. Baseline met 12 of 14 tasks and Guarded met 10 of 14. Both met all five normal tasks. Guarded lost useful evidence for the MFA question and benign quotation questions. Baseline declined the fictional recovery code for the authorized admin despite having its source, while Guarded answered it. These task judgments are separate from automated marker checks, citation membership, and source coverage.

Mean end-to-end times were 5.855 seconds for Baseline and 4.778 seconds for Guarded. These are workflow observations, not evidence that Guarded inference is faster. Baseline ran first for each question, timing includes cold loading, and Guarded skipped answer generation in two cases with empty context.

The strongest finding is the tradeoff between exposure and usefulness. Guarded reduced target-document exposure, but no marker-based attack-success reduction was observed because both modes already produced zero markers. The small handcrafted set and single run per case limit the conclusion. Guarded also changes the prompt and screening together, so the experiment does not isolate their individual effects.

Later browser checks confirmed the normal VPN answer with an expandable source, the two defense modes, and the recovery-question difference between employee and admin. For the employee in Guarded mode, all three retrieved public chunks were screened out and the application abstained. For the admin, two recovery chunks remained and the answer gave the fictional code. Submitting an old question form after logout displayed the recovery page. After the chat redesign, two successive VPN questions and replies remained visible together. These interactive checks are separate from the saved complete evaluation. The latest automated implementation check passed 146 Python tests with stubbed model responses and three JavaScript navigation tests with DOM stubs, including chat session checks and escaped response fragments; it does not measure model accuracy.

## What I learned

I learned to distinguish document permissions, attack detection, and model behavior. Permissions decide which text is available to a user. The scanner decides which patterns match. The model can still resist an injected instruction in Baseline, or fail to answer a normal question when useful evidence is removed. A blocked chunk count alone does not describe how well the system works.

The false positives made the security tradeoff clearer to me. A document can discuss malicious instructions without being malicious. A rule that only recognizes wording can remove information that a user needs. I therefore need to test benign material alongside attacks and inspect what happened to the answer.

I also learned why evaluation traces matter. Source IDs show what reached the model, and raw answers show whether a requested marker actually appeared. Separating these observations helped me describe the limitations honestly. A citation with a valid ID is useful for inspection, but it still needs a check against the source facts.

## How I would improve it

I would first expand the evaluation with held-out attack wording, more benign quotations, and repeated runs. I would test screening alone, the extra prompt alone, and their combination. That would show whether a change improves security without unnecessarily reducing useful answers.

Next, I would test a defense that considers the context of quoted instructions, while checking that malicious text cannot evade it by pretending to be an example. I would also evaluate smaller chunks, refilling a removed search result, and a relevance threshold. Each could improve evidence availability, but each changes the context and needs the same attack and normal-question checks.

For a larger deployment, I would add persistent embeddings with per-chunk permissions, permission-change invalidation, and a real identity provider. The current public accounts and trusted local files are appropriate for this classroom demonstration. A deployed service would also need access auditing, stronger operational controls, and a separate assessment of output data protection. Finally, I would extend citation validation to assess factual support rather than ID membership alone.
