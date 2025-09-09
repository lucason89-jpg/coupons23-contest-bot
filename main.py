# main.py
# Contest Bot per Coupons23 Premium (Polling)
import os, asyncio, sqlite3, random
from typing import List, Union
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters import CommandStart, Command

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("Manca BOT_TOKEN")

CHANNELS_RAW = os.getenv("CHANNELS", "")
if not CHANNELS_RAW:
    raise RuntimeError("Manca CHANNELS")

CHANNELS: List[Union[str,int]] = []
for part in [c.strip() for c in CHANNELS_RAW.split(",") if c.strip()]:
    if part.startswith("@"): CHANNELS.append(part)
    else:
        try: CHANNELS.append(int(part))
        except: CHANNELS.append(part)

ADMIN_IDS = set()
admins_raw = os.getenv("ADMIN_IDS", "").strip()
if admins_raw:
    for a in admins_raw.split(","):
        try: ADMIN_IDS.add(int(a.strip()))
        except: pass

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

db = sqlite3.connect("contest.db")
db.execute("CREATE TABLE IF NOT EXISTS participants(user_id INTEGER PRIMARY KEY, username TEXT, ticket INTEGER, joined_at TEXT)")
db.execute("CREATE TABLE IF NOT EXISTS winners(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, username TEXT, ticket INTEGER, drawn_at TEXT)")
db.commit()

async def is_member(user_id:int)->bool:
    for ch in CHANNELS:
        try:
            m = await bot.get_chat_member(ch, user_id)
            if m.status not in ("member","administrator","creator"): return False
        except: return False
    return True

def assign_ticket(user_id:int, username:str)->int:
    cur=db.execute("SELECT ticket FROM participants WHERE user_id=?",(user_id,))
    row=cur.fetchone()
    if row: return int(row[0])
    cur=db.execute("SELECT COALESCE(MAX(ticket),0)+1 FROM participants")
    t=int(cur.fetchone()[0])
    db.execute("INSERT INTO participants(user_id,username,ticket,joined_at) VALUES(?,?,?,datetime('now'))",(user_id,username,t))
    db.commit()
    return t

@dp.message(CommandStart())
async def start(m:Message):
    kb=InlineKeyboardBuilder()
    for ch in CHANNELS:
        try:
            chat=await bot.get_chat(ch)
            url=f"https://t.me/{chat.username}" if chat.username else f"https://t.me/c/{str(chat.id).replace('-100','')}"
            text=chat.title or str(ch)
            kb.button(text=text,url=url)
        except: kb.button(text=str(ch),url="https://t.me/")
    kb.button(text="🎟️ PARTECIPA ORA",callback_data="join")
    kb.adjust(1)
    prize=os.getenv("PRIZE_TEXT","Buono Amazon 🎁")
    intro=f"Benvenuto nel contest di Coupons23 Premium!\n\nIn palio: {prize}\n\n1) Entra nei canali qui sotto\n2) Poi premi 🎟️ PARTECIPA ORA"
    await m.answer(intro,reply_markup=kb.as_markup())

@dp.callback_query(F.data=="join")
async def join(cb:CallbackQuery):
    if not await is_member(cb.from_user.id):
        missing_channels = []
for channel in CHANNELS:
    member = await bot.get_chat_member(channel.strip(), user.id)
    if member.status in ["left", "kicked"]:
        missing_channels.append(channel.strip())

    missing_channels = []
    for channel in CHANNELS:
        try:
            member = await bot.get_chat_member(channel.strip(), user.id)
            if member.status in ["left", "kicked"]:
                missing_channels.append(channel.strip())
        except:
            missing_channels.append(channel.strip())

    if missing_channels:
        missing_list = "\n".join([f"- {ch}" for ch in missing_channels])
        await message.answer(f"⚠️ Non sei ancora iscritto a:\n{missing_list}")
        return


        return
    t=assign_ticket(cb.from_user.id, cb.from_user.username or "")
    await cb.message.answer(f"✅ Registrato! Il tuo numero è #{t:04d}. Usa /mystatus per rivederlo.")

@dp.message(Command("mystatus"))
async def mystatus(m:Message):
    cur=db.execute("SELECT ticket FROM participants WHERE user_id=?",(m.from_user.id,))
    row=cur.fetchone()
    if not row: await m.answer("Non sei registrato, premi PARTECIPA ORA.")
    else: await m.answer(f"🎟️ Il tuo numero: #{row[0]:04d}")

@dp.message(Command("draw"))
async def draw(m:Message):
    if ADMIN_IDS and m.from_user.id not in ADMIN_IDS: return
    rows=db.execute("SELECT user_id,username,ticket FROM participants").fetchall()
    if not rows: await m.answer("Nessun partecipante"); return
    random.shuffle(rows)
    for uid,uname,t in rows:
        if await is_member(uid):
            db.execute("INSERT INTO winners(user_id,username,ticket,drawn_at) VALUES(?,?,?,datetime('now'))",(uid,uname,t))
            db.commit()
            try: await bot.send_message(uid,f"🎉 Hai vinto! Ticket #{t:04d}")
            except: pass
            await m.answer(f"🏆 Vincitore: #{t:04d} – @{uname or uid}")
            return
    await m.answer("Nessun valido iscritto trovato.")

async def main(): await dp.start_polling(bot)
if __name__=="__main__": asyncio.run(main())
