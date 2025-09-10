
import os, asyncio, sqlite3, random
from typing import List, Union
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters import CommandStart, Command

# --- Config da ENV ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("Manca BOT_TOKEN")

CHANNELS_RAW = os.getenv("CHANNELS", "").strip()
if not CHANNELS_RAW:
    raise RuntimeError("Manca CHANNELS")

# Consente @username o ID numerici -100...
CHANNELS: List[Union[str, int]] = []
for part in [c.strip() for c in CHANNELS_RAW.split(",") if c.strip()]:
    if part.startswith("@"):
        CHANNELS.append(part)
    else:
        try:
            CHANNELS.append(int(part))
        except ValueError:
            CHANNELS.append(part)

ADMIN_IDS = set()
admins_raw = os.getenv("ADMIN_IDS", "").strip()
if admins_raw:
    for a in admins_raw.split(","):
        a = a.strip()
        if a:
            try:
                ADMIN_IDS.add(int(a))
            except ValueError:
                pass

PRIZE_TEXT = os.getenv("PRIZE_TEXT", "Buono Amazon 🎁")

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# --- DB SQLite semplice ---
db = sqlite3.connect("contest.db")
db.execute("""
CREATE TABLE IF NOT EXISTS participants(
  user_id INTEGER PRIMARY KEY,
  username TEXT,
  ticket INTEGER,
  joined_at TEXT
)""")
db.execute("""
CREATE TABLE IF NOT EXISTS winners(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER,
  username TEXT,
  ticket INTEGER,
  drawn_at TEXT
)""")
db.commit()


async def is_member(user_id: int) -> bool:
    """True se l'utente è iscritto a TUTTI i canali richiesti."""
    for ch in CHANNELS:
        try:
            m = await bot.get_chat_member(ch, user_id)
            if m.status not in ("member", "administrator", "creator"):
                return False
        except Exception:
            return False
    return True


async def missing_memberships(user_id: int) -> List[str]:
    """Ritorna la lista dei canali a cui NON è iscritto."""
    missing = []
    for ch in CHANNELS:
        label = None
        try:
            m = await bot.get_chat_member(ch, user_id)
            ok = (m.status in ("member", "administrator", "creator"))
        except Exception:
            ok = False
        try:
            chat = await bot.get_chat(ch)
            label = f"@{chat.username}" if chat.username else (chat.title or str(ch))
        except Exception:
            label = str(ch)
        if not ok:
            missing.append(label)
    return missing


def assign_ticket(user_id: int, username: str) -> int:
    cur = db.execute("SELECT ticket FROM participants WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    if row:
        return int(row[0])
    cur = db.execute("SELECT COALESCE(MAX(ticket),0)+1 FROM participants")
    t = int(cur.fetchone()[0])
    db.execute(
        "INSERT INTO participants(user_id,username,ticket,joined_at) VALUES(?,?,?,datetime('now'))",
        (user_id, username, t),
    )
    db.commit()
    return t


@dp.message(CommandStart())
async def cmd_start(m: Message):
    kb = InlineKeyboardBuilder()
    for ch in CHANNELS:
        try:
            chat = await bot.get_chat(ch)
            url = f"https://t.me/{chat.username}" if chat.username else f"https://t.me/c/{str(chat.id).replace('-100','')}"
            text = chat.title or (f"@{chat.username}" if chat.username else str(ch))
            kb.button(text=text, url=url)
        except Exception:
            kb.button(text=str(ch), url="https://t.me/")
    kb.button(text="🎟️ PARTECIPA ORA", callback_data="join")
    kb.adjust(1)

    intro = (
        "Benvenuto nel contest di **Coupons23 Premium**!\n\n"
        f"In palio: **{PRIZE_TEXT}**\n\n"
        "1) Entra nei canali qui sotto\n"
        "2) Poi premi **🎟️ PARTECIPA ORA**"
    )
    await m.answer(intro, reply_markup=kb.as_markup(), parse_mode="Markdown")


@dp.callback_query(F.data == "join")
async def on_join(cb: CallbackQuery):
    # Mostra CHIARAMENTE quali canali mancano
    missing = await missing_memberships(cb.from_user.id)
    if missing:
        lista = "\n".join(f"- {x}" for x in missing)
        msg = (
            f"⚠️ Non sei ancora iscritto a:\n{lista}\n\n"
            "Entra nei canali e poi riprova con **PARTECIPA ORA**."
        )
        await cb.message.answer(msg, parse_mode="Markdown")
        await cb.answer()
        return

    # Tutto ok → assegna ticket
    t = assign_ticket(cb.from_user.id, cb.from_user.username or "")
    await cb.message.answer(
        f"✅ Iscrizione verificata!\nIl tuo numero è **#{t:04d}**.\n"
        "Resta iscritto fino all’estrazione. Usa **/mystatus** per rivederlo.",
        parse_mode="Markdown",
    )
    await cb.answer("Registrato!")


@dp.message(Command("mystatus"))
async def mystatus(m: Message):
    cur = db.execute("SELECT ticket FROM participants WHERE user_id=?", (m.from_user.id,))
    row = cur.fetchone()
    if not row:
        await m.answer("Non risulti registrato. Premi **PARTECIPA ORA** nel bot.", parse_mode="Markdown")
        return
    await m.answer(f"🎟️ Il tuo numero: **#{int(row[0]):04d}**", parse_mode="Markdown")


@dp.message(Command("draw"))
async def draw(m: Message):
    if ADMIN_IDS and m.from_user.id not in ADMIN_IDS:
        return
    rows = db.execute("SELECT user_id, username, ticket FROM participants ORDER BY ticket").fetchall()
    if not rows:
        await m.answer("Nessun partecipante registrato.")
        return
    random.shuffle(rows)
    for uid, uname, t in rows:
        if await is_member(int(uid)):
            db.execute(
                "INSERT INTO winners(user_id, username, ticket, drawn_at) VALUES(?,?,?,datetime('now'))",
                (uid, uname or "", t),
            )
            db.commit()
            try:
                await bot.send_message(uid, f"🎉 Complimenti! Hai vinto il contest.\nTicket: #{int(t):04d}")
            except Exception:
                pass
            tag = f"@{uname}" if uname else f"id:{uid}"
            await m.answer(f"🏆 Vincitore: **#{int(t):04d}** – {tag}", parse_mode="Markdown")
            return
    await m.answer("Nessun partecipante attualmente iscritto ai canali richiesti. Estrazione annullata.")


async def main():
    print("Bot starting (polling)...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
