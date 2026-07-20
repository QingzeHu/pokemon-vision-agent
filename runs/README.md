# Published run data

Raw data from the runs cited in the article. Each directory contains the
complete console log (`run.log`: timestamped model reasoning, thinking
summaries, button presses, notes updates, and per-call token/cost accounting)
and the final agent state (`agent_state.json`: notes, summary, counters).
`debug_frames/` (official run only) holds every screenshot exactly as the
model saw it.

| Directory | Model | Game | What it is |
|---|---|---|---|
| `fable5-firered/` | claude-fable-5 | FireRed (Chinese fan translation) | **The official run in the article**: 2,000 turns, Boulder Badge at turn 1,785, $73.50 all-in, one uninterrupted session on 2026-07-13. Includes all 2,000 frames. |
| `fable5/` | claude-fable-5 | Crystal (Chinese fan translation) | The control run: 763 turns across three fresh starts (mid-run restarts replay the game; notes persist), never crossed Route 29; ended on API credit exhaustion. Cost accounting starts mid-log (the usage logger landed mid-run). |
| `local-firered/` | qwen3.6-35b-a3b (LM Studio) | FireRed (Chinese fan translation) | Local-model comparison run; source of the qwen key-press statistics. |
| `local-qwen3.6-stuck/` | qwen3.6-35b-a3b (LM Studio) | Crystal (Chinese fan translation) | The early run whose notes death-spiral ("All movement directions fail") motivated the notes-are-hypotheses prompt rule; also the "Professor Oak's Lab" hallucination cited in the article. |
| `opus/` | claude-opus-4-8 | Crystal (Chinese fan translation) | Short informal test run (246 presses), used for the key-sequence comparison. |

The non-official runs predate the frozen protocol by up to a day and ran on
slightly earlier revisions of the harness; treat them as context, not as
controlled comparisons. The official run's request shape is asserted by
`test_request_shape.py` (`make test`).
