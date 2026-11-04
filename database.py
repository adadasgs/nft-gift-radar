import os
import aiosqlite

DB_PATH = os.getenv("DATABASE_PATH", "radar.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS chats (
    chat_id INTEGER PRIMARY KEY,
    title TEXT,
    topic_5 INTEGER,
    topic_10 INTEGER,
    topic_20 INTEGER,
    topic_35 INTEGER,
    topic_60 INTEGER,
    enabled INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS lots (
    source TEXT NOT NULL,
    source_id TEXT NOT NULL,
    title TEXT NOT NULL,
    price REAL NOT NULL,
    currency TEXT NOT NULL,
    lot_url TEXT,
    image_url TEXT,
    status TEXT NOT NULL DEFAULT 'listed',
    first_seen TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    chat_id INTEGER,
    message_id INTEGER,
    reserved_by INTEGER,
    reserved_username TEXT,
    reserved_at TEXT,
    PRIMARY KEY (source, source_id)
);
CREATE INDEX IF NOT EXISTS idx_lots_status ON lots(status);
"""

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(SCHEMA)
        await db.commit()

async def add_chat(chat_id: int, title: str, topics: dict):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO chats(chat_id,title,topic_5,topic_10,topic_20,topic_35,topic_60)
               VALUES(?,?,?,?,?,?,?)
               ON CONFLICT(chat_id) DO UPDATE SET title=excluded.title,
               topic_5=excluded.topic_5, topic_10=excluded.topic_10,
               topic_20=excluded.topic_20, topic_35=excluded.topic_35,
               topic_60=excluded.topic_60, enabled=1""",
            (chat_id, title, topics["5"], topics["10"], topics["20"], topics["35"], topics["60"]),
        )
        await db.commit()

async def get_chats():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM chats WHERE enabled=1")
        return [dict(r) for r in await cur.fetchall()]

async def get_lot(source: str, source_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM lots WHERE source=? AND source_id=?", (source, source_id))
        row = await cur.fetchone()
        return dict(row) if row else None

async def save_lot(lot: dict, chat_id: int, message_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT OR IGNORE INTO lots
            (source,source_id,title,price,currency,lot_url,image_url,chat_id,message_id)
            VALUES(?,?,?,?,?,?,?,?,?)""",
            (lot["source"], lot["source_id"], lot["title"], lot["price"], lot["currency"],
             lot.get("lot_url"), lot.get("image_url"), chat_id, message_id),
        )
        await db.commit()

async def reserve_lot(source: str, source_id: str, user_id: int, username: str | None):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """UPDATE lots SET reserved_by=?,reserved_username=?,reserved_at=CURRENT_TIMESTAMP
               WHERE source=? AND source_id=? AND reserved_by IS NULL AND status='listed'""",
            (user_id, username, source, source_id),
        )
        await db.commit()
        if cur.rowcount != 1:
            return None
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM lots WHERE source=? AND source_id=?", (source, source_id))
        return dict(await cur.fetchone())

async def release_lot(source: str, source_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "UPDATE lots SET reserved_by=NULL,reserved_username=NULL,reserved_at=NULL WHERE source=? AND source_id=?",
            (source, source_id),
        )
        await db.commit()
        return cur.rowcount == 1

async def set_lot_status(source: str, source_id: str, status: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE lots SET status=? WHERE source=? AND source_id=?", (status, source, source_id))
        await db.commit()
