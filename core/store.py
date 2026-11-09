# -*- coding: utf-8 -*-
"""SQLite 存档：文章、每日期次、推送状态。"""
import json
import os
import sqlite3

from core.config import path

SCHEMA = """
CREATE TABLE IF NOT EXISTS articles (
    id          TEXT PRIMARY KEY,      -- url 的 sha1
    date        TEXT NOT NULL,         -- 内容日 YYYY-MM-DD
    source      TEXT,
    channel     TEXT,
    title       TEXT,
    url         TEXT,
    body        TEXT,
    score       INTEGER,
    payload     TEXT,                  -- analysis 的 JSON
    created_at  TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_articles_date ON articles(date);

CREATE TABLE IF NOT EXISTS editions (
    date        TEXT PRIMARY KEY,
    status      TEXT,                  -- built / pushed / failed
    picked      TEXT,                  -- article id 的 JSON 数组
    pushed_at   TEXT,
    attempt     INTEGER DEFAULT 0
);
"""


def connect():
    db_path = path("data", "app.db")
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def save_articles(records, date_str):
    conn = connect()
    with conn:
        for rec in records:
            conn.execute(
                "INSERT OR REPLACE INTO articles"
                "(id,date,source,channel,title,url,body,score,payload)"
                " VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    rec["id"], date_str, rec.get("source"), rec.get("channel"),
                    rec.get("title"), rec.get("url"), rec.get("body", ""),
                    rec["analysis"]["score"],
                    json.dumps(rec["analysis"], ensure_ascii=False),
                ),
            )
    conn.close()


def get_article(article_id):
    conn = connect()
    row = conn.execute("SELECT * FROM articles WHERE id=?", (article_id,)).fetchone()
    conn.close()
    if not row:
        return None
    art = dict(row)
    art["analysis"] = json.loads(art["payload"] or "{}")
    return art


def list_dates(limit=60):
    conn = connect()
    rows = conn.execute(
        "SELECT date, COUNT(*) AS n FROM articles GROUP BY date ORDER BY date DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def list_by_date(date_str):
    conn = connect()
    rows = conn.execute(
        "SELECT * FROM articles WHERE date=? ORDER BY score DESC", (date_str,)
    ).fetchall()
    conn.close()
    out = []
    for row in rows:
        art = dict(row)
        art["analysis"] = json.loads(art["payload"] or "{}")
        out.append(art)
    return out


def save_edition(date_str, status, picked_ids):
    conn = connect()
    with conn:
        conn.execute(
            "INSERT INTO editions(date,status,picked) VALUES(?,?,?)"
            " ON CONFLICT(date) DO UPDATE SET status=excluded.status, picked=excluded.picked",
            (date_str, status, json.dumps(picked_ids)),
        )
    conn.close()


def get_edition(date_str):
    conn = connect()
    row = conn.execute("SELECT * FROM editions WHERE date=?", (date_str,)).fetchone()
    conn.close()
    return dict(row) if row else None


def mark_pushed(date_str):
    conn = connect()
    with conn:
        conn.execute(
            "UPDATE editions SET status='pushed', pushed_at=datetime('now','localtime'),"
            " attempt=attempt+1 WHERE date=?",
            (date_str,),
        )
    conn.close()
