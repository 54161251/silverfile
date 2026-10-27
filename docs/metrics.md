# Context Strategy Measurements (spec 4.5)

Batch: the 10 W-2 images in `data/fixtures/batch/` for one household (A24, D1), processed in order in one session by `python run.py batch`. Each document is read by the production Extraction agent (OCR), then Intake's document briefing calls the model (`src/agents/intake_briefing.py`, prompt `src/prompts/document_briefing.md`).

- **Disabled** (`--no-context-strategy`): every earlier document and briefing is resent.
- **Enabled** (default, D3 selective recall): the current document plus a code-built summary of session decisions that does not grow with the number of documents.

## Actual input tokens (API usage)

Not measured yet: run both commands with a key in `.env` (`SILVERFILE_MODEL`, `ANTHROPIC_API_KEY`).

## Estimated input tokens (offline, no API call)

Characters / 4, including the system prompt; earlier briefings replaced by a 300-character stand-in. These are estimates, not API usage.

| Document | Strategy disabled (full history) | Strategy enabled (selective recall) |
|---|---:|---:|
| 1 (w2_batch_01) | 420 | 437 |
| 2 (w2_batch_02) | 552 | 462 |
| 3 (w2_batch_03) | 684 | 463 |
| 4 (w2_batch_04) | 815 | 463 |
| 5 (w2_batch_05) | 948 | 464 |
| 6 (w2_batch_06) | 1,082 | 465 |
| 7 (w2_batch_07) | 1,215 | 464 |
| 8 (w2_batch_08) | 1,348 | 464 |
| 9 (w2_batch_09) | 1,481 | 464 |
| 10 (w2_batch_10) | 1,618 | 467 |

Strategy disabled: document 1 = 420 tokens, document 10 = 1,618 tokens (3.9x).

Strategy enabled: document 1 = 437 tokens, document 10 = 467 tokens (1.1x).

## Reproduce

```sh
python run.py batch --no-context-strategy
python run.py batch
```

Each run saves `runtime/metrics/<actual|estimated>_<strategy>.json` and rebuilds this page.
