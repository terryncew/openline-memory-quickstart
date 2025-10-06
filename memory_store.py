# memory_store.py — SQLite (default) or in-memory fallback for MemoryItems
import os, sqlite3, json
from typing import List, Optional, Dict

class MemoryStore:
    def __init__(self):
        self.use_sqlite = os.getenv("USE_SQLITE", "1") == "1"
        if self.use_sqlite:
            path = os.getenv("SQLITE_PATH", "memory.db")
            self.conn = sqlite3.connect(path, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
            self._init()
        else:
            self._mem: Dict[str, dict] = {}
            self._revoked = set()

    def _init(self):
        c = self.conn.cursor()
        c.execute("""
        CREATE TABLE IF NOT EXISTS memories (
          mid TEXT PRIMARY KEY,
          text TEXT NOT NULL,
          tags TEXT NOT NULL,      -- JSON list
          scope TEXT NOT NULL,
          consent TEXT NOT NULL,
          created_at TEXT NOT NULL,
          expires_at TEXT,
          rid TEXT NOT NULL,
          revoked INTEGER NOT NULL DEFAULT 0
        )""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_mem_created ON memories(created_at)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_mem_revoked ON memories(revoked)")
        self.conn.commit()

    def write(self, item: dict):
        if self.use_sqlite:
            c = self.conn.cursor()
            c.execute("""INSERT INTO memories
              (mid,text,tags,scope,consent,created_at,expires_at,rid,revoked)
              VALUES (?,?,?,?,?,?,?,?,0)""",
              (item["mid"], item["text"], json.dumps(item["tags"]), item["scope"],
               item["consent"], item["created_at"], item["expires_at"], item["rid"]))
            self.conn.commit()
        else:
            self._mem[item["mid"]] = item

    def search(self, q: str, tags: Optional[List[str]], top_k: int = 5):
        out = []
        if self.use_sqlite:
            c = self.conn.cursor()
            like = f"%{(q or '').lower()}%"
            if tags:
                tag_like = "%" + tags[0] + "%"
                rows = c.execute("""
                  SELECT * FROM memories
                  WHERE revoked=0 AND LOWER(text) LIKE ? AND tags LIKE ?
                  ORDER BY created_at DESC LIMIT ?""", (like, tag_like, max(1, min(top_k, 20)))).fetchall()
            else:
                rows = c.execute("""
                  SELECT * FROM memories
                  WHERE revoked=0 AND LOWER(text) LIKE ?
                  ORDER BY created_at DESC LIMIT ?""", (like, max(1, min(top_k, 20)))).fetchall()
            for r in rows:
                out.append({"mid": r["mid"], "snippet": (r["text"] or "")[:240],
                            "tags": json.loads(r["tags"] or "[]"), "created_at": r["created_at"]})
            return out
        # in-memory
        for it in self._mem.values():
            if it["mid"] in self._revoked: continue
            if (q.lower() in it["text"].lower()) or (tags and any(t in it["tags"] for t in tags)):
                out.append({"mid": it["mid"], "snippet": it["text"][:240],
                            "tags": it["tags"], "created_at": it["created_at"]})
        out.sort(key=lambda x: x["created_at"], reverse=True)
        return out[:max(1, min(top_k, 20))]

    def revoke(self, mid: str) -> str:
        if self.use_sqlite:
            c = self.conn.cursor()
            row = c.execute("SELECT rid FROM memories WHERE mid=? AND revoked=0", (mid,)).fetchone()
            if not row: return ""
            c.execute("UPDATE memories SET revoked=1 WHERE mid=?", (mid,))
            self.conn.commit()
            return row["rid"]
        if mid not in self._mem or mid in self._revoked: return ""
        self._revoked.add(mid)
        return self._mem[mid]["rid"]
