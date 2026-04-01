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

# --- 1. START COMMAND ---
@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    user_name = message.from_user.first_name
    await message.reply_text(
        f"👋 **Hi {user_name}!**\n\n"
        "Main Super-Fast Compressor hoon. 🚀\n"
        "Video bhejein, main use turant Rename aur Compress kar dunga."
    )

# --- 2. PROGRESS BAR (Less updates = More Speed) ---
async def progress(current, total, message, text):
    try:
        percent = current * 100 / total
        # Sirf har 15% pe update taaki network block na ho
        if int(percent) % 15 == 0: 
            bar = "▓" * int(percent/10) + "░" * (10 - int(percent/10))
            await message.edit_text(f"{text}\n\n{bar} {round(percent, 2)}%")
    except: pass

# --- 3. LIVE STATUS ---
async def track_compression(process, message, total_duration, out_file):
    last_percent = -1
    while process.poll() is None:
        try:
            if os.path.exists("ffmpeg_log.txt"):
                with open("ffmpeg_log.txt", "r") as f:
                    log = f.read()
                    times = re.findall(r"time=(\d+:\d+:\d+\.\d+)", log)
                    if times:
                        last_time = times[-1]
                        h, m, s = map(float, last_time.split(':'))
                        curr_dur = h * 3600 + m * 60 + s
                        percent = int((curr_dur / total_duration) * 100)
                        if percent >= last_percent + 15: 
                            size = os.path.getsize(out_file) / (1024 * 1024) if os.path.exists(out_file) else 0
                            await message.edit_text(f"🚀 **Fast Compressing...**\n\n📊 Done: {percent}%\n📦 Size: `{round(size, 2)} MB`")
                            last_percent = percent
        except: pass
        await asyncio.sleep(15)

# --- 4. WORKFLOW ---
@app.on_message(filters.private & (filters.video | filters.document))
async def handle_video(client, message):
    file = message.video or message.document
    msg = await message.reply_text("⚡ **Downloading...**")
    path = await client.download_media(message, progress=progress, progress_args=(msg, "📥 Downloading..."))
    user_data[message.from_user.id] = {"path": path, "size": file.file_size / (1024*1024)}
    await msg.edit_text("✅ Downloaded!\n\n📂 **Ab Naya Naam (Rename) bhejein:**")

@app.on_message(filters.private & filters.text & ~filters.command(["start", "skip"]))
async def get_name(client, message):
    uid = message.from_user.id
    if uid in user_data and "name" not in user_data[uid]:
        user_data[uid]["name"] = message.text
        await message.reply_text("🖼️ **Ab Thumbnail bhejein ya /skip karein:**")

@app.on_message(filters.private & (filters.photo | filters.command("skip")))
async def get_thumb(client, message):
    uid = message.from_user.id
    if uid not in user_data: return
    if message.photo:
        user_data[uid]["thumb"] = await client.download_media(message.photo)
        await message.reply_text("✅ **Thumbnail Saved Successfully!**")
    else:
        user_data[uid]["thumb"] = None
        await message.reply_text("⏩ **Thumbnail Skipped.**")
    
    size = user_data[uid]["size"]
    options = [1500, 1200, 1000, 700, 500, 400, 300, 200, 100]
    btns = []
    row = []
    for opt in options:
        if opt < size:
            row.append(InlineKeyboardButton(f"{opt}MB", callback_data=str(opt)))
            if len(row) == 3: btns.append(row); row = []
    if row: btns.append(row)
    await message.reply_text("🎯 **Target Size select karein:**", reply_markup=InlineKeyboardMarkup(btns))

# --- 5. ULTRA-SPEED ENGINE ---
@app.on_callback_query()
async def process_video(client, query):
    uid = query.from_user.id
    data = user_data.get(uid)
    if not data: return
    target_mb = int(query.data)
    out = data['name']
    if "." not in out: out += ".mp4"
    msg = await query.message.edit_text(f"⚙️ **Processing to {target_mb}MB...**")
    
    try:
        ff_path, fp_path = "ffmpeg", "ffprobe"
        probe = subprocess.check_output([fp_path, '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', data['path']])
        duration = float(probe)
        bitrate = int((target_mb * 8192) / duration)
        
        # --- SPEED TUNING ---
        # -preset ultrafast : Max Speed
        # -sn : No subtitles (Saves time)
        # -threads 0 : Use all CPU cores
        # -bufsize : Faster buffer management
        cmd = f'{ff_path} -i "{data["path"]}" -b:v {bitrate}k -vcodec libx264 -preset ultrafast -threads 0 -bufsize {bitrate*2}k -sn "{out}" -y > ffmpeg_log.txt 2>&1'
        
        process = subprocess.Popen(cmd, shell=True)
        await track_compression(process, msg, duration, out)
        process.wait()
        
        try:
            p_probe = subprocess.check_output([fp_path, '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', out])
            v_dur = int(float(p_probe))
        except: v_dur = 0

        await msg.edit_text("📤 **Uploading...**")
        await client.send_video(
            chat_id=query.message.chat.id, video=out, duration=v_dur,
            thumb=data.get("thumb"), caption=f"📂 `{out}`",
            supports_streaming=True, progress=progress, progress_args=(msg, "📤 Uploading...")
        )
    except Exception as e:
        await msg.edit_text(f"❌ Error: {e}")
    
    if os.path.exists("ffmpeg_log.txt"): os.remove("ffmpeg_log.txt")
    for f in [data['path'], out, data.get("thumb")]:
        if f and os.path.exists(f): os.remove(f)
    user_data.pop(uid, None)

app.run()
