import os
import subprocess
import asyncio
import re
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# --- CONFIG ---
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")

app = Client("VideoCompressorBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
user_data = {}

# --- START ---
@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    user_name = message.from_user.first_name
    await message.reply_text(f"👋 Hi {user_name}!\n\nSend video → Rename → Compress 🚀")

# --- PROGRESS ---
async def progress(current, total, message, text):
    try:
        percent = current * 100 / total
        if int(percent) % 15 == 0:
            bar = "▓" * int(percent/10) + "░" * (10 - int(percent/10))
            await message.edit_text(f"{text}\n\n{bar} {round(percent,2)}%")
    except:
        pass

# --- TRACK ---
async def track_compression(process, message, total_duration, out_file):
    last_percent = -1
    while process.poll() is None:
        try:
            if os.path.exists("ffmpeg_log.txt"):
                with open("ffmpeg_log.txt", "r") as f:
                    log = f.read()
                    times = re.findall(r"time=(\d+:\d+:\d+\.\d+)", log)
                    if times:
                        h, m, s = map(float, times[-1].split(':'))
                        curr = h*3600 + m*60 + s
                        percent = int((curr / total_duration) * 100)

                        if percent >= last_percent + 15:
                            size = os.path.getsize(out_file)/(1024*1024) if os.path.exists(out_file) else 0
                            await message.edit_text(
                                f"🚀 Compressing...\n\n📊 {percent}%\n📦 {round(size,2)} MB"
                            )
                            last_percent = percent
        except:
            pass
        await asyncio.sleep(15)

# --- RECEIVE VIDEO ---
@app.on_message(filters.private & (filters.video | filters.document))
async def handle_video(client, message):
    msg = await message.reply_text("📥 Downloading...")

    path = await client.download_media(
        message,
        progress=progress,
        progress_args=(msg, "📥 Downloading...")
    )

    user_data[message.from_user.id] = {"path": path}

    await msg.edit_text("✅ Downloaded!\n\n📂 Send new file name:")

# --- GET NAME ---
@app.on_message(filters.private & filters.text & ~filters.command(["start", "skip"]))
async def get_name(client, message):
    uid = message.from_user.id
    if uid in user_data and "name" not in user_data[uid]:
        user_data[uid]["name"] = message.text
        await message.reply_text("🖼 Send thumbnail or /skip")

# --- THUMB + BUTTONS ---
@app.on_message(filters.private & (filters.photo | filters.command("skip")))
async def get_thumb(client, message):
    uid = message.from_user.id
    if uid not in user_data:
        return

    if message.photo:
        user_data[uid]["thumb"] = await client.download_media(message.photo)
    else:
        user_data[uid]["thumb"] = None

    btns = [
        [
            InlineKeyboardButton("🔥 1500MB", callback_data="1500"),
            InlineKeyboardButton("🔥 1200MB", callback_data="1200"),
        ],
        [
            InlineKeyboardButton("⚖️ 800MB", callback_data="800"),
            InlineKeyboardButton("⚖️ 700MB", callback_data="700"),
        ],
        [
            InlineKeyboardButton("📦 500MB", callback_data="500"),
            InlineKeyboardButton("📦 400MB", callback_data="400"),
        ]
    ]

    await message.reply_text("🎯 Select target size:", reply_markup=InlineKeyboardMarkup(btns))

# --- PROCESS ---
@app.on_callback_query()
async def process_video(client, query):
    uid = query.from_user.id
    data = user_data.get(uid)
    if not data:
        return

    target_mb = int(query.data)

    # 🔥 QUALITY LOGIC
    if target_mb >= 1200:
        crf = 20
        preset = "medium"
    elif target_mb >= 700:
        crf = 23
        preset = "veryfast"
    else:
        crf = 26
        preset = "veryfast"

    out = data["name"]
    if "." not in out:
        out += ".mp4"

    msg = await query.message.edit_text(f"⚙️ Processing {target_mb}MB...")

    try:
        ff_path, fp_path = "ffmpeg", "ffprobe"

        duration = float(subprocess.check_output([
            fp_path, '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            data['path']
        ]))

        bitrate = int((target_mb * 8192) / duration)

        # 🔥 FINAL COMMAND (ALL SAFE)
        cmd = f'''{ff_path} -i "{data["path"]}" 
-map 0 
-c:v libx264 
-preset {preset} 
-crf {crf} 
-maxrate {bitrate}k 
-bufsize {bitrate*2}k 
-movflags +faststart 
-c:a copy 
-c:s copy 
-threads 0 
"{out}" -y > ffmpeg_log.txt 2>&1'''

        process = subprocess.Popen(cmd, shell=True)
        await track_compression(process, msg, duration, out)
        process.wait()

        await msg.edit_text("📤 Uploading...")

        await client.send_video(
            chat_id=query.message.chat.id,
            video=out,
            duration=int(duration),
            thumb=data.get("thumb"),
            caption=f"📂 {out}",
            supports_streaming=True,
            progress=progress,
            progress_args=(msg, "📤 Uploading...")
        )

    except Exception as e:
        await msg.edit_text(f"❌ Error: {e}")

    # --- CLEANUP ---
    if os.path.exists("ffmpeg_log.txt"):
        os.remove("ffmpeg_log.txt")

    for f in [data['path'], out, data.get("thumb")]:
        if f and os.path.exists(f):
            os.remove(f)

    user_data.pop(uid, None)

# --- RUN ---
app.run()
