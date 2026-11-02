# Benchmarks

`longmemeval_compare.py` measures agent-memory's session recall on LongMemEval, a public benchmark of long
conversations with questions about them. It calls no model and no network service, and it ships with no data and no
results file: you fetch the dataset yourself, so the number you get is one you reproduced.

1. Get the cleaned small set, `longmemeval_s_cleaned.json`, from the LongMemEval project (the project's own repository
   links to it; it is published as the Hugging Face dataset at https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned).
2. From a clone of this repository:

```sh
python3 -I benchmarks/longmemeval_compare.py longmemeval_s_cleaned.json --out my-run.json
```

It ranks sessions three ways with agent-memory's own search rules (`fts_terms` in `session_continuity.py`: all
terms first, any term only when nothing matches, BM25 over FTS5 with the porter tokenizer) and prints recall_any@5
and @10 for each. `--mempalace results.jsonl` adds another system's published per-question results beside them, if
you have that file.
