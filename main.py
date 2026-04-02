import os
import subprocess
import asyncio
import re
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# --- CONFIGURATION (Environment Variables) ---
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")

app = Client("VideoCompressorBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
user_data = {}

# --- PROGRESS BAR HELPER ---
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
                            size = os.path.getsize(out_file)/(1024*1024) if os.path.exists(out_file) else 0
                            await message.edit_text(f"🚀 Compressing...\n\n📊 Progress: {percent}%\n📦 Size: {round(size,2)} MB")
                            last_percent = percent
        except:
            pass
        await asyncio.sleep(10)

# --- COMMANDS ---
@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    await message.reply_text("👋 Hi!\nSend a video to start compressing. 🚀")

# --- FILE RECEIVER ---
@app.on_message(filters.private & (filters.video | filters.document))
async def handle_video(client, message):
    msg = await message.reply_text("📥 Downloading...")
    path = await client.download_media(
        message,
        progress=progress,
        progress_args=(msg, "📥 Downloading...")
    )
    user_data[message.from_user.id] = {"path": path}
    await msg.edit_text("✅ Downloaded!\n\n📂 Send the **New File Name** (e.g. video.mp4):")

# --- FILE NAME HANDLER ---
@app.on_message(filters.private & filters.text & ~filters.command(["start", "skip"]))
async def get_name(client, message):
    uid = message.from_user.id
    if uid in user_data and "name" not in user_data[uid]:
        user_data[uid]["name"] = message.text
        await message.reply_text("🖼 Send a thumbnail or /skip")

# --- THUMBNAIL & SIZE BUTTONS ---
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
        btns = [[InlineKeyboardButton("🔥 1.5GB", callback_data="1500"), InlineKeyboardButton("🔥 1.2GB", callback_data="1200")]]
    elif size >= 900:
        btns = [[InlineKeyboardButton("⚖️ 800MB", callback_data="800"), InlineKeyboardButton("⚖️ 600MB", callback_data="600")]]
    else:
        btns = [[InlineKeyboardButton("📦 400MB", callback_data="400"), InlineKeyboardButton("📦 300MB", callback_data="300")]]

    await message.reply_text(f"📏 Size: {round(size, 2)} MB\n🎯 Target Size:", reply_markup=InlineKeyboardMarkup(btns))

# --- CORE PROCESSING ---
@app.on_callback_query()
async def process_video(client, query):
    uid = query.from_user.id
    data = user_data.get(uid)
    if not data: return

    target_mb = int(query.data)
    crf = 24 if target_mb >= 700 else 27
    preset = "veryfast"

    out = f"final_{uid}.mp4"
    msg = await query.message.edit_text(f"⚙️ Compressing to {target_mb}MB...")

    try:
        # Get duration using ffprobe
        fp_cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", data['path']]
        duration = float(subprocess.check_output(fp_cmd).decode().strip())
        
        # Calculate Bitrate
        bitrate = int((target_mb * 8192) / duration)

        # 🔥 FIXED COMMAND (Single String for Shell Compatibility)
        cmd = (
            f'ffmpeg -i "{data["path"]}" -map 0 '
            f'-c:v libx264 -preset {preset} -crf {crf} '
            f'-pix_fmt yuv420p -profile:v high -level 4.1 '
            f'-maxrate {bitrate}k -bufsize {bitrate*2}k -movflags +faststart '
            f'-c:a aac -b:a 128k -c:s copy -threads 0 "{out}" -y > ffmpeg_log.txt 2>&1'
        )

        process = subprocess.Popen(cmd, shell=True)
        await track_compression(process, msg, duration, out)
        process.wait()

        if not os.path.exists(out) or os.path.getsize(out) < 1000:
            await msg.edit_text("❌ Compression Failed. Check logs.")
            return

        await msg.edit_text("📤 Uploading...")
        
        await client.send_video(
            chat_id=query.message.chat.id,
            video=out,
            duration=int(duration),
            thumb=data.get("thumb"),
            caption=f"✅ **Compressed**\n\n📂 **Name:** `{data['name']}`\n🎯 **Target:** {target_mb}MB",
            supports_streaming=True,
            progress=progress,
            progress_args=(msg, "📤 Uploading...")
        )
        await msg.delete()

    except Exception as e:
        await msg.edit_text(f"❌ Error: {str(e)}")

    # CLEANUP
    if os.path.exists("ffmpeg_log.txt"): os.remove("ffmpeg_log.txt")
    for f in [data['path'], out, data.get("thumb")]:
        if f and os.path.exists(f):
            try: os.remove(f)
            except: pass
    user_data.pop(uid, None)

# --- RUN ---
if __name__ == "__main__":
    app.run()
