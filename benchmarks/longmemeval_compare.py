#!/usr/bin/env python3
"""LongMemEval session recall: agent-memory's search against MemPalace's published raw run.

Uses MemPalace's protocol for its headline 96.6% (benchmarks/longmemeval_bench.py, raw mode, session
granularity): 500 questions, one document per haystack session made of the user's turns joined, the question
as the query, and a hit when any answer session is in the top k (recall_any@k). Only the ranking differs.

- today: agent-memory's session recall rules on those documents. fts_terms() words, all terms first, any
  term only when nothing matches, bm25 over an FTS5 table with tokenize='porter unicode61'.
- per_message: the same rules on one row per user message, grouped by session on its best message, fetching
  max(k * 12, 24) rows as recall_sessions() does. This is closer to how agent-memory indexes sessions.
- any_word: every query ranks by any term, the change agent-si 1.11.0 made to its search.

No model, network or personal data. Fetch the public dataset yourself (longmemeval_s_cleaned.json, from the
LongMemEval project; see benchmarks/README.md and https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned) and
pass it. Optionally pass MemPalace's per-question results file for the same run to compare question by question.

    python3 -I benchmarks/longmemeval_compare.py longmemeval_s_cleaned.json [--mempalace results.jsonl] [--out x.json]
"""
import argparse
import collections
import json
import sqlite3
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from session_continuity import fts_terms  # noqa: E402

KS = (5, 10)


def session_docs(entry):
    """MemPalace's session corpus: each haystack session's user turns, joined, skipping sessions without one."""
    docs = []
    for session, sid in zip(entry["haystack_sessions"], entry["haystack_session_ids"]):
        turns = [turn["content"] for turn in session if turn["role"] == "user"]
        if turns:
            docs.append((sid, turns))
    return docs


def expressions(question):
    terms = fts_terms(question)
    quoted = ['"%s"' % term.replace('"', '""') for term in terms]
    return " ".join(quoted), " OR ".join(quoted), len(terms)


def rank_sessions(docs, question, mode):
    con = sqlite3.connect(":memory:")
    con.execute("CREATE VIRTUAL TABLE t USING fts5(body, sid UNINDEXED, tokenize='porter unicode61')")
    rows = ([(" \n".join(turns), sid) for sid, turns in docs] if mode != "per_message"
            else [(text, sid) for sid, turns in docs for text in turns])
    con.executemany("INSERT INTO t (body, sid) VALUES (?, ?)", rows)
    every, anyword, count = expressions(question)
    if not count:
        return {k: [] for k in KS}

    def query(expression, limit=None):
        sql = "SELECT sid, bm25(t) FROM t WHERE t MATCH ? ORDER BY bm25(t), rowid"
        return con.execute(sql + (" LIMIT ?" if limit else ""), (expression, limit) if limit else (expression,)).fetchall()

    ranked = {}
    for k in KS:
        limit = max(k * 12, 24) if mode == "per_message" else None
        found = query(anyword, limit) if mode == "any_word" else query(every, limit)
        if not found and mode != "any_word" and count > 1:
            found = query(anyword, limit)
        best = {}
        for sid, score in found:
            best[sid] = min(score, best.get(sid, score))
        ranked[k] = sorted(best, key=lambda sid: (best[sid], sid))[:k]
    con.close()
    return ranked


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("data")
    parser.add_argument("--mempalace", help="MemPalace's per-question results JSONL for the same run")
    parser.add_argument("--out")
    args = parser.parse_args()
    data = json.loads(Path(args.data).read_text(encoding="utf-8"))
    modes = ("today", "per_message", "any_word")
    hits = {mode: {k: {} for k in KS} for mode in modes}
    started = time.monotonic()
    for entry in data:
        answers, docs = set(entry["answer_session_ids"]), session_docs(entry)
        for mode in modes:
            ranked = rank_sessions(docs, entry["question"], mode)
            for k in KS:
                hits[mode][k][entry["question_id"]] = any(sid in answers for sid in ranked[k])
    seconds = round(time.monotonic() - started, 1)
    if args.mempalace:
        hits["mempalace_raw"] = {k: {} for k in KS}
        for line in Path(args.mempalace).read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            session = row["retrieval_results"]["metrics"]["session"]
            for k in KS:
                hits["mempalace_raw"][k][row["question_id"]] = bool(session[f"recall_any@{k}"])
    types = {entry["question_id"]: entry["question_type"] for entry in data}
    summary = {"questions": len(data), "seconds": seconds, "recall_any": {}, "by_type_at_5": {}}
    for mode, per_k in hits.items():
        summary["recall_any"][mode] = {f"@{k}": round(sum(per_k[k].values()) / len(per_k[k]), 3) for k in KS}
        by_type = collections.defaultdict(list)
        for qid, hit in per_k[5].items():
            by_type[types[qid]].append(hit)
        summary["by_type_at_5"][mode] = {t: f"{sum(v)} of {len(v)}" for t, v in sorted(by_type.items())}
    if "mempalace_raw" in hits:
        for mode in modes:
            ours, theirs = hits[mode][5], hits["mempalace_raw"][5]
            summary.setdefault("vs_mempalace_at_5", {})[mode] = {
                "both": sum(ours[q] and theirs[q] for q in ours), "only_ours": sum(ours[q] and not theirs[q] for q in ours),
                "only_mempalace": sum(theirs[q] and not ours[q] for q in ours), "neither": sum(not ours[q] and not theirs[q] for q in ours)}
    print(json.dumps(summary, indent=1))
    if args.out:
        detail = {mode: {f"@{k}": per_k[k] for k in KS} for mode, per_k in hits.items()}
        Path(args.out).write_text(json.dumps({"summary": summary, "hits": detail}, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
