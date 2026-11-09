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

It ranks sessions five ways. The `recall_sessions` arm calls agent-memory's real session recall
(`recall_sessions` in `session_continuity.py`: any term, BM25 over FTS5 with the porter tokenizer, one row per
message). The others reimplement the ranking on one document per session or one row per message, with all terms
first or any term, for comparison.

It prints two metrics for each, labelled. `recall_all@5` and `@10` are strict, the benchmark's own metric: every
answer session in the top k, on the 470 answerable questions. Quote this one. `recall_any@5` and `@10` are any-hit,
the easier metric: at least one answer session in the top k, on all 500 questions. Any-hit is not the strict number.

`--mempalace results.jsonl` adds another system's published per-question results beside them, if you have that file.
