import os
import subprocess
import asyncio
import re
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# --- CONFIGURATION ---
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")

app = Client("VideoCompressorBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
user_data = {}

# --- PROGRESS BAR ---
async def progress(current, total, message, text):
    try:
        percent = current * 100 / total
        if int(percent) % 15 == 0:
            bar = "▓" * int(percent/10) + "░" * (10 - int(percent/10))
            await message.edit_text(f"{text}\n\n{bar} {round(percent, 2)}%")
    except:
        pass

# --- COMPRESSION TRACKER ---
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
                        if percent >= last_percent + 10: 
                            await message.edit_text(f"🚀 Compressing... {percent}%")
                            last_percent = percent
        except:
            pass
        await asyncio.sleep(8)

# --- START ---
@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    await message.reply_text("👋 Hi Shakeel!\nSend video to start. 🚀")

# --- RECEIVE VIDEO ---
@app.on_message(filters.private & (filters.video | filters.document))
async def handle_video(client, message):
    msg = await message.reply_text("📥 Downloading...")
    path = await client.download_media(message, progress=progress, progress_args=(msg, "📥 Downloading..."))
    user_data[message.from_user.id] = {"path": path}
    await msg.edit_text("✅ Downloaded!\n\n📂 Ab sirf **Naya Naam** bhejein (without .mp4):")

# --- RENAME HANDLER (Fix: Only Name) ---
@app.on_message(filters.private & filters.text & ~filters.command(["start", "skip"]))
async def get_name(client, message):
    uid = message.from_user.id
    if uid in user_data and "name" not in user_data[uid]:
        # Hum user ke naam ke peeche .mp4 khud laga denge
        user_data[uid]["name"] = f"{message.text}.mp4"
        await message.reply_text("🖼 Ab thumbnail photo bhejein ya /skip karein:")

# --- THUMBNAIL & BUTTONS ---
@app.on_message(filters.private & (filters.photo | filters.command("skip")))
async def get_thumb(client, message):
    uid = message.from_user.id
    if uid not in user_data: return

    if message.photo:
        user_data[uid]["thumb"] = await client.download_media(message.photo)
    else:
        user_data[uid]["thumb"] = None

    size = os.path.getsize(user_data[uid]["path"]) / (1024 * 1024)
    btns = [[InlineKeyboardButton("📦 400MB", callback_data="400"), InlineKeyboardButton("📦 300MB", callback_data="300")]]
    await message.reply_text(f"📏 File Size: {round(size, 2)} MB\n🎯 Target Size select karein:", reply_markup=InlineKeyboardMarkup(btns))

# --- PROCESSING (Fix: File Generation) ---
@app.on_callback_query()
async def process_video(client, query):
    uid = query.from_user.id
    data = user_data.get(uid)
    if not data: return

    target_mb = int(query.data)
    out = f"final_{uid}.mp4"
    msg = await query.message.edit_text(f"⚙️ Compressing to {target_mb}MB... Please wait.")

    try:
        # Get duration
        fp_cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", data['path']]
        duration = float(subprocess.check_output(fp_cmd).decode().strip())
        bitrate = int((target_mb * 8192) / duration)

        # 🔥 Speed fix: 'ultrafast' use kiya hai taaki jaldi ho
        cmd = (
            f'ffmpeg -i "{data["path"]}" -c:v libx264 -preset ultrafast -crf 27 '
            f'-b:v {bitrate}k -pix_fmt yuv420p -c:a aac -b:a 128k '
            f'-movflags +faststart "{out}" -y > ffmpeg_log.txt 2>&1'
        )

        process = subprocess.Popen(cmd, shell=True)
        await track_compression(process, msg, duration, out)
        process.wait()

        if not os.path.exists(out):
            await msg.edit_text("❌ Error: File nahi ban payi. Command fail ho gaya.")
            return

        await msg.edit_text("📤 Uploading...")
        await client.send_video(
            chat_id=query.message.chat.id,
            video=out,
            duration=int(duration),
            thumb=data.get("thumb"),
            caption=f"✅ **Done!**\n📂 `{data['name']}`",
            supports_streaming=True
        )
        await msg.delete()

    except Exception as e:
        await msg.edit_text(f"❌ Error: {str(e)}")

    # Cleanup
    for f in [data['path'], out, data.get("thumb"), "ffmpeg_log.txt"]:
        if f and os.path.exists(f): os.remove(f)
    user_data.pop(uid, None)

if __name__ == "__main__":
    app.run()
