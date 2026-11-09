#!/usr/bin/env python3
"""LongMemEval session recall: agent-memory's search against MemPalace's published raw run.

Uses MemPalace's protocol for its headline 96.6% (benchmarks/longmemeval_bench.py, raw mode, session
granularity): 500 questions, one document per haystack session made of the user's turns joined, the question
as the query, and a hit when any answer session is in the top k (recall_any@k). Only the ranking differs.

- all_first: fts_terms() words, all terms first, any term only when nothing matches, bm25 over an FTS5 table
  with tokenize='porter unicode61'. These were session recall's rules before it ranked by any term.
- any_word: every query ranks by any term, the change agent-si 1.11.0 made to its search.
- all_first_per_message, any_word_per_message: the same rules on one row per user message, grouped by session on
  its best message, fetching max(k * 12, 24) rows as recall_sessions() does.
- recall_sessions: the real recall_sessions() on a real session index holding one row per user message. The other
  arms only reuse fts_terms(), so this is the only one that moves when session_continuity.py changes.

Two metrics, labelled in the output, because they aren't interchangeable:
- recall_all@k (strict) is the benchmark's own metric: every answer session in the top k, on the 470 answerable
  questions. Quote this one.
- recall_any@k (any-hit) is the easier one: at least one answer session in the top k, on all 500 questions. Never
  quote it as the strict number.

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
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from session_continuity import connect, fts_terms, recall_sessions  # noqa: E402

KS = (5, 10)
MODES = ("all_first", "any_word", "all_first_per_message", "any_word_per_message", "recall_sessions")
METRICS = {
    "recall_all": "STRICT, the benchmark's metric: every answer session in the top k, on the answerable questions. Quote this one.",
    "recall_any": "ANY-HIT, easier: at least one answer session in the top k, on all questions. Not the strict number.",
}


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


def rank_with_recall_sessions(docs, question):
    with tempfile.TemporaryDirectory() as folder:
        db_path = Path(folder) / "sessions.db"
        con = connect(db_path)
        # The dataset repeats some session ids within a question, so sources are deduplicated and keys run on.
        con.executemany("INSERT OR IGNORE INTO session_sources (harness, session_id, source_path, fingerprint, title, cwd, started_at, updated_at) "
                        "VALUES ('bench', ?, '', '', '', '', 0, 0)", [(sid,) for sid, _ in docs])
        messages = [(sid, text) for sid, turns in docs for text in turns]
        con.executemany("INSERT INTO session_messages (harness, session_id, message_key, role, content, timestamp) "
                        "VALUES ('bench', ?, ?, 'user', ?, 0)", [(sid, str(n), text) for n, (sid, text) in enumerate(messages)])
        con.commit()
        con.close()
        return {k: [hit.session_id for hit in recall_sessions(db_path, question, limit=k, sync=False)] for k in KS}


def rank_sessions(docs, question, mode):
    if mode == "recall_sessions":
        return rank_with_recall_sessions(docs, question)
    per_message = mode.endswith("_per_message")
    con = sqlite3.connect(":memory:")
    con.execute("CREATE VIRTUAL TABLE t USING fts5(body, sid UNINDEXED, tokenize='porter unicode61')")
    rows = ([(text, sid) for sid, turns in docs for text in turns] if per_message
            else [(" \n".join(turns), sid) for sid, turns in docs])
    con.executemany("INSERT INTO t (body, sid) VALUES (?, ?)", rows)
    every, anyword, count = expressions(question)
    if not count:
        return {k: [] for k in KS}

    def query(expression, limit=None):
        sql = "SELECT sid, bm25(t) FROM t WHERE t MATCH ? ORDER BY bm25(t), rowid"
        return con.execute(sql + (" LIMIT ?" if limit else ""), (expression, limit) if limit else (expression,)).fetchall()

    ranked = {}
    for k in KS:
        limit = max(k * 12, 24) if per_message else None
        any_first = mode.startswith("any_word")
        found = query(anyword, limit) if any_first else query(every, limit)
        if not found and not any_first and count > 1:
            found = query(anyword, limit)
        best = {}
        for sid, score in found:
            best[sid] = min(score, best.get(sid, score))
        ranked[k] = sorted(best, key=lambda sid: (best[sid], sid))[:k]
    con.close()
    return ranked


def is_answerable(question_id):
    return not question_id.endswith("_abs")


def counted(hits):
    return f"{sum(hits.values())}/{len(hits)} = {sum(hits.values()) / len(hits):.2%}"


def by_type(hits, types):
    grouped = collections.defaultdict(list)
    for qid, hit in hits.items():
        grouped[types[qid]].append(hit)
    return {t: f"{sum(v)} of {len(v)}" for t, v in sorted(grouped.items())}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("data")
    parser.add_argument("--mempalace", help="MemPalace's per-question results JSONL for the same run")
    parser.add_argument("--out")
    args = parser.parse_args()
    data = json.loads(Path(args.data).read_text(encoding="utf-8"))
    hits = {metric: {mode: {k: {} for k in KS} for mode in MODES} for metric in METRICS}
    started = time.monotonic()
    for entry in data:
        qid, answers, docs = entry["question_id"], set(entry["answer_session_ids"]), session_docs(entry)
        for mode in MODES:
            ranked = rank_sessions(docs, entry["question"], mode)
            for k in KS:
                hits["recall_any"][mode][k][qid] = any(sid in answers for sid in ranked[k])
                if is_answerable(qid):
                    hits["recall_all"][mode][k][qid] = answers <= set(ranked[k])
    seconds = round(time.monotonic() - started, 1)
    if args.mempalace:
        hits["recall_any"]["mempalace_raw"], hits["recall_all"]["mempalace_raw"] = {k: {} for k in KS}, {k: {} for k in KS}
        for line in Path(args.mempalace).read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            session = row["retrieval_results"]["metrics"]["session"]
            for k in KS:
                hits["recall_any"]["mempalace_raw"][k][row["question_id"]] = bool(session[f"recall_any@{k}"])
                if is_answerable(row["question_id"]) and f"recall_all@{k}" in session:
                    hits["recall_all"]["mempalace_raw"][k][row["question_id"]] = bool(session[f"recall_all@{k}"])
    types = {entry["question_id"]: entry["question_type"] for entry in data}
    summary = {"questions": len(data), "answerable": sum(is_answerable(entry["question_id"]) for entry in data),
               "seconds": seconds, "metrics": METRICS}
    for metric, label in (("recall_all", "strict"), ("recall_any", "any_hit")):
        filled = {mode: per_k for mode, per_k in hits[metric].items() if per_k[5]}
        summary[f"{label}_{metric}"] = {mode: {f"@{k}": counted(per_k[k]) for k in KS} for mode, per_k in filled.items()}
        summary[f"{label}_by_type_at_5"] = {mode: by_type(per_k[5], types) for mode, per_k in filled.items()}
    if args.mempalace:
        for mode in MODES:
            ours, theirs = hits["recall_any"][mode][5], hits["recall_any"]["mempalace_raw"][5]
            summary.setdefault("any_hit_vs_mempalace_at_5", {})[mode] = {
                "both": sum(ours[q] and theirs[q] for q in ours), "only_ours": sum(ours[q] and not theirs[q] for q in ours),
                "only_mempalace": sum(theirs[q] and not ours[q] for q in ours), "neither": sum(not ours[q] and not theirs[q] for q in ours)}
    print(json.dumps(summary, indent=1))
    if args.out:
        detail = {metric: {mode: {f"@{k}": per_k[k] for k in KS} for mode, per_k in modes.items()} for metric, modes in hits.items()}
        Path(args.out).write_text(json.dumps({"summary": summary, "hits": detail}, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
