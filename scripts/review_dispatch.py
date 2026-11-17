"""One-shot review receipt drain for an existing scheduler; no timer installed."""
import argparse
import json
from pathlib import Path
from review_advance import continuation
from review_receipts import Receipts
from review_protocol import validate_round


def drain(root, round_path, output, model=None, allow_model=False):
    current = json.loads(Path(round_path).read_text(encoding='utf-8'))
    binding = validate_round(current)
    round_key = json.dumps([current[k] for k in ('task_id', 'stage', 'language', 'round_id')])
    handler = continuation(round_path, output, model=model, allow_model=allow_model)
    store = Receipts(root)
    try:
        store.repair_views()
        candidates = store.db.execute("SELECT id,receipt FROM receipts WHERE state='received' AND round_key=? ORDER BY id",
                                      (round_key,)).fetchall()
        rows = [row for row in candidates if json.loads(row['receipt']).get('content_sha256') == binding]
        stale = [row['id'] for row in candidates if row not in rows]
        results = []
        for row in rows:
            try:
                results.append(store.process(row["id"], handler))
            except Exception:
                results.append(store.status(row["id"]))
        return {"state": "processed" if rows else "no_change", "results": results,
                "stale_current_round_receipts": stale}
    finally:
        store.close()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", required=True)
    p.add_argument("--round", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--metadata-model")
    p.add_argument("--allow-metadata-model", action="store_true")
    a = p.parse_args()
    print(json.dumps(drain(a.root, a.round, a.out, a.metadata_model, a.allow_metadata_model), ensure_ascii=False))


if __name__ == "__main__":
    main()
