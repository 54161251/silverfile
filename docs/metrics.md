# Context Strategy Measurements (spec 4.5)

Batch: the 10 W-2 images in `data/fixtures/batch/` for one household (A24, D1), processed in order in one session by `python run.py batch`. Each document is read by the production Extraction agent (OCR), then Intake's document briefing calls the model (`src/agents/intake_briefing.py`, prompt `src/prompts/document_briefing.md`).

- **Disabled** (`--no-context-strategy`): every earlier document and briefing is resent.
- **Enabled** (default, D3 selective recall): the current document plus a code-built summary of session decisions that does not grow with the number of documents.

## Actual input tokens (API usage)

Reported by the API as `usage.input_tokens` plus cache tokens. Model: claude-opus-5-5.

| Document | Strategy disabled (full history) | Strategy enabled (selective recall) |
|---|---:|---:|
| 1 (w2_batch_01) | 906 | 928 |
| 2 (w2_batch_02) | 1,137 | 1,017 |
| 3 (w2_batch_03) | 1,369 | 1,039 |
| 4 (w2_batch_04) | 1,608 | 1,038 |
| 5 (w2_batch_05) | 1,846 | 1,039 |
| 6 (w2_batch_06) | 2,086 | 1,037 |
| 7 (w2_batch_07) | 2,294 | 1,040 |
| 8 (w2_batch_08) | 2,545 | 1,039 |
| 9 (w2_batch_09) | 2,789 | 1,040 |
| 10 (w2_batch_10) | 3,031 | 1,040 |

Strategy disabled: document 1 = 906 tokens, document 10 = 3,031 tokens (3.3x).

Strategy enabled: document 1 = 928 tokens, document 10 = 1,040 tokens (1.1x).

## Estimated input tokens (offline, no API call)

Characters / 4, including the system prompt; earlier briefings replaced by a 300-character stand-in. These are estimates, not API usage.

| Document | Strategy disabled (full history) | Strategy enabled (selective recall) |
|---|---:|---:|
| 1 (w2_batch_01) | not run | 439 |
| 2 (w2_batch_02) | not run | 463 |
| 3 (w2_batch_03) | not run | 464 |
| 4 (w2_batch_04) | not run | 465 |
| 5 (w2_batch_05) | not run | 464 |
| 6 (w2_batch_06) | not run | 466 |
| 7 (w2_batch_07) | not run | 465 |
| 8 (w2_batch_08) | not run | 465 |
| 9 (w2_batch_09) | not run | 465 |
| 10 (w2_batch_10) | not run | 464 |

Strategy enabled: document 1 = 439 tokens, document 10 = 464 tokens (1.1x).

## Reproduce

```sh
python run.py batch --no-context-strategy
python run.py batch
```

Each run saves `runtime/metrics/<actual|estimated>_<strategy>.json` and rebuilds this page.
