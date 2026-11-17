"""Durable local review transport; stores receipts, not production task status.

Callers supply the current round read from the existing authoritative task file.
No provider calls or scheduling. Processing callbacks must be idempotent by
receipt_id; their unknown external outcomes must not be blindly retried.
"""
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile

from review_protocol import validate_receipt


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def atomic(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def immutable(path, data):
    path = Path(path)
    if path.exists():
        if path.read_text(encoding="utf-8") != data:
            raise ValueError("archive conflict; existing file preserved")
        return
    atomic(path, data)


def segment(value):
    if not isinstance(value, str) or not re.fullmatch(r"[\w-]{1,120}", value):
        raise ValueError("unsafe filename component")
    return value


class Receipts:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.root / "review-receipts.sqlite3", timeout=10)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("""CREATE TABLE IF NOT EXISTS receipts (
          id TEXT PRIMARY KEY, round_key TEXT UNIQUE NOT NULL, receipt TEXT NOT NULL,
          route TEXT NOT NULL, page TEXT NOT NULL, archive TEXT NOT NULL,
          state TEXT NOT NULL, error TEXT, result TEXT)""")
        self.db.commit()

    def close(self):
        self.db.close()

    def receive(self, current, receipt, *, entry, page):
        """Return received only after committing the receipt and saved page snapshot."""
        route = validate_receipt(current, receipt, entry=entry)
        if not isinstance(page, str) or not page.strip():
            raise ValueError("review page snapshot required")
        round_key = json.dumps([current[k] for k in ("task_id", "stage", "language", "round_id")])
        date = receipt["submitted_at"][:10]
        # Include language: the example filename alone collides for multilingual rounds.
        name = "-".join([date.replace("-", ""), current["stage"], segment(current["task_id"]),
                         segment(current["language"]), segment(current["version"]), segment(current["round_id"])])
        archive = str(Path("reviews") / date[:7] / segment(current["batch"]) / name)
        self.db.execute("BEGIN IMMEDIATE")
        try:
            old = self.db.execute("SELECT * FROM receipts WHERE round_key=?", (round_key,)).fetchone()
            if old and old["id"] != route["receipt_id"]:
                raise ValueError("round already submitted with a different decision; open a new round")
            if not old:
                self.db.execute("INSERT INTO receipts VALUES (?,?,?,?,?,?,?,NULL,NULL)",
                                (route["receipt_id"], round_key, encode(receipt), encode(route), page, archive, "received"))
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        self.repair_views()
        return self.status(route["receipt_id"])

    def status(self, ident):
        row = self.db.execute("SELECT id,state,error,result FROM receipts WHERE id=?", (ident,)).fetchone()
        if row is None:
            raise ValueError("unknown receipt")
        return dict(row)

    def repair_views(self):
        """Rebuild derived files after interrupted writes; DB commit is acceptance."""
        self.db.execute("BEGIN IMMEDIATE")
        try:
            rows = self.db.execute("SELECT * FROM receipts ORDER BY archive,id").fetchall()
            index = ["# 审核索引", "", "| 审核页 | 收据 | 任务/阶段/语种/轮次 |", "| --- | --- | --- |"]
            for row in rows:
                signal = self.root / "review-signals" / (row["id"] + ".json")
                if row["state"] not in ("completed", "archiving"):
                    immutable(signal, row["receipt"])
                    continue
                page = self.root / (row["archive"] + ".html")
                receipt = page.with_name("review-" + page.stem + ".json")
                immutable(page, row["page"])
                immutable(receipt, row["receipt"])
                if signal.exists():
                    if signal.read_text(encoding="utf-8") != row["receipt"]:
                        raise ValueError("signal changed; preserved for inspection")
                    signal.unlink()
                relative_page = page.relative_to(self.root / "reviews").as_posix()
                relative_receipt = receipt.relative_to(self.root / "reviews").as_posix()
                index.append(f"| [{page.stem}]({relative_page}) | [JSON]({relative_receipt}) | {row['round_key']} |")
            atomic(self.root / "reviews/INDEX.md", "\n".join(index) + "\n")
            self.db.execute("UPDATE receipts SET state='completed',error=NULL WHERE state='archiving'")
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

    def process(self, ident, handler):
        """Claim once; failed is retryable, processing requires explicit recovery.

        Handler gets the original receipt and validated routes; it must return
        only after next-stage artifacts are durably saved, using receipt_id as
        idempotency key. This module cannot authorize external production.
        """
        self.db.execute("BEGIN IMMEDIATE")
        row = self.db.execute("SELECT * FROM receipts WHERE id=?", (ident,)).fetchone()
        if row is None:
            self.db.rollback()
            raise ValueError("unknown receipt")
        if row["state"] in ("completed", "processing", "archiving"):
            self.db.commit()
            self.repair_views()
            return self.status(ident)
        self.db.execute("UPDATE receipts SET state='processing',error=NULL WHERE id=?", (ident,))
        self.db.commit()
        try:
            result = handler(json.loads(row["receipt"]), json.loads(row["route"]))
            serialized = encode(result)
        except Exception as exc:
            # Do not store exception text: provider exceptions can contain secrets.
            with self.db:
                self.db.execute("UPDATE receipts SET state='failed',error=? WHERE id=?", (type(exc).__name__, ident))
            raise
        with self.db:
            self.db.execute("UPDATE receipts SET state='archiving',result=?,error=NULL WHERE id=?", (serialized, ident))
        self.repair_views()
        return self.status(ident)
