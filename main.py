import os
import subprocess
import asyncio
import re
import time
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

# --- TRACK COMPRESSION ---
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
                            size = os.path.getsize(out_file)/(1024*1024) if os.path.exists(out_file) else 0
                            await message.edit_text(f"🚀 Compressing: {percent}%\n📦 Size: {round(size,2)} MB")
                            last_percent = percent
        except:
            pass
        await asyncio.sleep(10)

# --- START ---
@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    await message.reply_text("👋 Hi Shakeel!\nSend a video to begin. 🚀")

# --- RECEIVE VIDEO ---
@app.on_message(filters.private & (filters.video | filters.document))
async def handle_video(client, message):
    msg = await message.reply_text("📥 Downloading...")
    path = await client.download_media(message, progress=progress, progress_args=(msg, "📥 Downloading..."))
    user_data[message.from_user.id] = {"path": path}
    await msg.edit_text("✅ Downloaded!\n\n📂 Send the **New File Name** (No extension needed):")

# --- RENAME HANDLER ---
@app.on_message(filters.private & filters.text & \~filters.command(["start", "skip"]))
async def get_name(client, message):
    uid = message.from_user.id
    if uid in user_data and "raw_name" not in user_data[uid]:
        user_data[uid]["raw_name"] = message.text
        user_data[uid]["name"] = f"{message.text}.mp4"
        await message.reply_text("🖼 Send a thumbnail photo or /skip")

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
    
    if size >= 1800:
        btns = [[InlineKeyboardButton("🔥 1500MB", callback_data="1500"), InlineKeyboardButton("🔥 1200MB", callback_data="1200")]]
    elif size >= 900:
        btns = [[InlineKeyboardButton("⚖️ 800MB", callback_data="800"), InlineKeyboardButton("⚖️ 600MB", callback_data="600")]]
    elif size >= 500:
        btns = [[InlineKeyboardButton("📦 400MB", callback_data="400"), InlineKeyboardButton("📦 350MB", callback_data="350")]]
    else:
        btns = [[InlineKeyboardButton("📦 300MB", callback_data="300"), InlineKeyboardButton("📦 250MB", callback_data="250")]]

    await message.reply_text(f"📏 Current: {round(size, 2)} MB\n🎯 Select Target Size:", reply_markup=InlineKeyboardMarkup(btns))

# --- CORE COMPRESSION (Updated for High Quality + Target Size) ---
@app.on_callback_query()
async def process_video(client, query):
    uid = query.from_user.id
    data = user_data.get(uid)
    if not data: return

    target_mb = int(query.data)
    out = f"vid_{uid}_{int(time.time())}.mp4"

    msg = await query.message.edit_text(f"⚙️ High Quality Compression to {target_mb}MB...\n⏳ Processing (Quality Priority)...")

    try:
        # Get duration using ffprobe
        fp_cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", data['path']]
        duration = float(subprocess.check_output(fp_cmd).decode().strip())
        
        if duration <= 0:
            await msg.edit_text("❌ Could not get video duration!")
            return

        # Bitrate calculation for target size
        bitrate = int((target_mb * 8192) / duration)

        # Smart CRF & Preset for MINIMAL quality loss
        if target_mb >= 1000:          # 1200MB or 1500MB
            crf = 22
            preset = "faster"
        elif target_mb >= 600:         # 600MB - 800MB
            crf = 23
            preset = "veryfast"
        elif target_mb >= 350:         # 350MB - 400MB
            crf = 24
            preset = "veryfast"
        else:                          # 250MB - 300MB
            crf = 25
            preset = "veryfast"

        # 🔥 IMPROVED COMMAND (High Quality + Better Speed)
        cmd = (
            f'ffmpeg -i "{data["path"]}" -c:v libx264 -preset {preset} -crf {crf} '
            f'-b:v {bitrate}k -maxrate {int(bitrate * 1.2)}k -bufsize {int(bitrate * 2.5)}k '
            f'-pix_fmt yuv420p -profile:v high -level 4.1 '
            f'-movflags +faststart -c:a aac -b:a 96k '
            f'-threads 2 "{out}" -y > ffmpeg_log.txt 2>&1'
        )

        process = subprocess.Popen(cmd, shell=True)
        await track_compression(process, msg, duration, out)
        process.wait()

        # Check if file exists and is not empty
        if not os.path.exists(out) or os.path.getsize(out) < 1000:
            if os.path.exists("ffmpeg_log.txt"):
                with open("ffmpeg_log.txt", "r") as f:
                    err_log = f.read()[-300:] 
                await msg.edit_text(f"❌ FFmpeg Error Log:\n`{err_log}`")
            else:
                await msg.edit_text("❌ Error: Output file not generated.")
            return

        final_size = os.path.getsize(out) / (1024 * 1024)
        await msg.edit_text(f"📤 Uploading... ({round(final_size, 2)} MB)")
        
        await client.send_video(
            chat_id=query.message.chat.id,
            video=out,
            duration=int(duration),
            thumb=data.get("thumb"),
            caption=f"✅ **Done!**\n📂 `{data['raw_name']}`\n📊 Size: {round(final_size, 2)} MB\n🎥 Quality: High (Minimal Loss)",
            supports_streaming=True,
            progress=progress,
            progress_args=(msg, "📤 Uploading...")
        )
        await msg.delete()

    except Exception as e:
        await msg.edit_text(f"❌ System Error: {str(e)}")

    # CLEANUP
    if os.path.exists("ffmpeg_log.txt"): os.remove("ffmpeg_log.txt")
    for file in [data.get('path'), out, data.get("thumb")]:
        if file and os.path.exists(file):
            try: os.remove(file)
            except: pass
    user_data.pop(uid, None)

# --- RUN ---
if __name__ == "__main__":
    app.run()
