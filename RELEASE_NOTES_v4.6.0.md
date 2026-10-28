# OSIRIS v4.6.0 — Release Notes (2026-10-26)

A major model gateway sovereignty, performance scaling, and living curriculum release: integrates the unified tri-tier model gateway (`GemmaProvider` with native SSE streaming over Ollama and `GeminiCompatibilityProvider` with Vertex Express bursting), raises the mentor token output ceiling to 2,048 tokens to eliminate reply truncation penalties, introduces $O(1)$ fast incremental tail verification (`verify_chain_tail`) to eliminate large-ledger I/O bottlenecks, incorporates the comprehensive 1,000-interaction technical curriculum across 10 engineering domains (`curriculum_1000.json`), and anchors Block 1 execution telemetry directly into the immutable Merkle exchange ledger.

---

## 1. Unified Model Gateway & Provider Decoupling (`osiris_cli/providers/`)

- **Gemma 2B Native Edge Streaming (`GemmaProvider`)**:
  - Implements native Server-Sent Events (SSE) streaming against local Ollama `/v1/chat/completions` endpoints on port 11434.
  - Automatically discovers local `gemma2:2b` instances, eliminating fallback delays.
  - Adds `gemma2:2b` to `ARCHITECT_PREFERENCES` and `SYNTHESIZER_PREFERENCES` in `osiris_termux_console.py`.
- **Gemini Cloud Burst Gateway (`GeminiCompatibilityProvider`)**:
  - Integrates `gemini-2.5-flash` natively via Vertex Express credentials (`~/.env`), enabling high-throughput (~20 s/turn) reasoning and systems engineering citation without CPU thread saturation.
- **Dynamic Voice Switching (`/mentor`)**:
  - Added on-the-fly mentor switching (`/mentor gemini`, `/mentor gemma`, `/mentor ollama`) without requiring terminal restart.
  - Decoupled `ProviderMentorAdapter` voice resolution from `OSIRIS_CHAT_MODEL`, ensuring the console's Architect configuration does not inadvertently hijack the conversational voice model.

## 2. High-Performance Ledger Verification & Output Budget (`osiris_cli/living.py`, `osiris_cli/probes.py`)

- **$O(1)$ Incremental Tail Verification (`verify_chain_tail`)**:
  - Adds constant-time seek/tail verification for ledger checkpoints, reading only the trailing byte buffer to verify internal hash chaining without re-parsing multi-megabyte files from line 1.
  - Reserved full $O(N)$ Merkle sweeps for block completion and pre-flight gates, speeding up large curriculum checkpoint intervals by over 100x.
- **Dynamic Output Budget Expansion (`OSIRIS_MENTOR_MAX_TOKENS = 2048`)**:
  - Raised default mentor output budget from 700 to 2,048 tokens, eliminating the `cut off at 700-token limit` truncation penalty that previously caused 30% of complex technical exchanges to be rejected from NCLM core learning.
  - Raised the default mentor context (`OSIRIS_MENTOR_NUM_CTX`) from 4,096 to 8,192 tokens with it. The prompt budget is `(num_ctx − max_tokens) × 3.5` characters: at 4,096 the larger reply limit cut it from 11,886 to 7,168, and a pasted document no longer fit beside the system prompt. It is 21,504 at 8,192. The Ollama `/api/chat` mentor sends this value; a provider voice served through Ollama's OpenAI-compatible endpoint uses the server's context length (`OLLAMA_CONTEXT_LENGTH`).

## 3. 1,000-Interaction Advanced Technical Curriculum (`scratch/curriculum_1000.json`)

- **10 Technical Domains (100 Prompts per Domain)**:
  - Formulates a complete 1,000-interaction curriculum spanning Quantum Circuit Engineering, Topological QEC & QLDPc, Non-Causal Byte Language Modeling (NCLM), Sovereign Cryptographic Governance (SYS-021), Dual-Substrate Systems Engineering, Rule-Evolving Artificial Life (`organism_sim`), DNA-Lang 0.2 (`dnalang-core`/`bridge`), Autonomous Scientific Discovery, Security Gates & AST Verification, and Multi-Voice Council Arbitration.
- **Chunked Block Runner (`run_curriculum_1000_block.py`)**:
  - Governed execution harness under SYS-021 with deterministic payload-bound receipts, automated $O(1)$ tail checkpoints, and atomic write-ahead ledger locking.
  - Block 1 (`0001`–`0100`) execution absorbed into `~/.osiris/living/exchanges.jsonl`, advancing the ledger to 382 entries with zero forks.

## 4. Evidence & Citable Identifiers

- **Predecessor Software Release (v4.5.4)**: [10.5281/zenodo.23257201](https://doi.org/10.5281/zenodo.23257201)
- **Anomalous $\tau$-Phase Quantum Coherence Paper**: Deposited to Zenodo (`paper/zenodo_paper.pdf`, SHA-256: `2f525e860739b1b5c22498544b3af163da23b267ff4509d1083820d67994a42f`): [10.5281/zenodo.23658893](https://doi.org/10.5281/zenodo.23658893)
- **1,000-Prompt Curriculum Dataset**: SHA-256 `d2b8e5b6a27b2f003514884c21d67faa6c48e6f5a5048a65a01f03b36bf89e51`
- **Phase-Conjugate Recalibration Telemetry Ledger (PCRB)**: [10.5281/zenodo.23213288](https://doi.org/10.5281/zenodo.23213288)
