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

app = Client("ShakeelMasterBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
user_data = {}

# --- PROGRESS BAR (Download/Upload ke liye) ---
async def progress(current, total, message, text):
    try:
        percent = current * 100 / total
        bar = "▓" * int(percent/10) + "░" * (10 - int(percent/10))
        await message.edit_text(f"{text}\n\n{bar} {round(percent, 2)}%")
    except: pass

# --- LIVE COMPRESSION TRACKER (No Flood Wait Version) ---
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
                        
                        # Sirf tab update karein jab 5% ka fark aaye (Flood wait se bachne ke liye)
                        if percent >= last_percent + 5:
                            size = os.path.getsize(out_file) / (1024 * 1024) if os.path.exists(out_file) else 0
                            bar = "🟩" * int(percent/10) + "⬜" * (10 - int(percent/10))
                            
                            await message.edit_text(
                                f"⚙️ **Compression in Progress...**\n\n"
                                f"{bar} {percent}%\n"
                                f"📊 Processed: `{round(size, 2)} MB`\n"
                                f"⏳ Current Time: `{last_time}`"
                            )
                            last_percent = percent
        except: pass
        await asyncio.sleep(15) # 15 second ka gap taaki Telegram block na kare

# --- 1. SETUP & STATUS ---
@app.on_message(filters.command("set_ffmpeg") & filters.private)
async def ask_ffmpeg(client, message):
    await message.reply_text("📁 **Shakeel Bhai, ab FFmpeg/FFprobe ki binary file bhejein:**")

@app.on_message(filters.private & filters.document & ~filters.video)
async def save_binary(client, message):
    name = message.document.file_name
    if name in ["ffmpeg", "ffprobe"]:
        path = await client.download_media(message, file_name=f"./{name}")
        os.chmod(path, 0o755)
        await message.reply_text(f"✅ `{name}` set ho gaya!")
    else:
        await message.reply_text("❌ Sirf `ffmpeg` ya `ffprobe` binary bhejein.")

@app.on_message(filters.command("status") & filters.private)
async def status(client, message):
    f = "✅" if os.path.exists("./ffmpeg") else "❌"
    p = "✅" if os.path.exists("./ffprobe") else "❌"
    await message.reply_text(f"**System Status:**\nFFmpeg: {f}\nFFprobe: {p}")

# --- 2. WORKFLOW (Video -> Name -> Thumb) ---
@app.on_message(filters.private & (filters.video | filters.document))
async def handle_video(client, message):
    if not os.path.exists("./ffmpeg"):
        return await message.reply_text("❌ Pehle `/set_ffmpeg` se binaries set karein!")

    file = message.video or message.document
    msg = await message.reply_text("📥 **Downloading...**")
    path = await client.download_media(message, progress=progress, progress_args=(msg, "📥 **Downloading...**"))
    
    user_data[message.from_user.id] = {"path": path, "size": file.file_size / (1024*1024)}
    await msg.edit_text("✅ Downloaded!\n\n📂 **Ab Naya Naam (Rename) bhejein:**")

@app.on_message(filters.private & filters.text & ~filters.command(["start", "status", "set_ffmpeg", "skip"]))
async def get_name(client, message):
    uid = message.from_user.id
    if uid in user_data and "name" not in user_data[uid]:
        user_data[uid]["name"] = message.text
        await message.reply_text("🖼️ **Ab Thumbnail (Photo) bhejein ya /skip karein:**")

@app.on_message(filters.private & (filters.photo | filters.command("skip")))
async def get_thumb(client, message):
    uid = message.from_user.id
    if uid not in user_data: return

    user_data[uid]["thumb"] = await client.download_media(message.photo) if message.photo else None
    
    size = user_data[uid]["size"]
    btns = []
    row = []
    for opt in [1500, 1000, 700, 500, 400, 300, 200, 100]:
        if opt < size:
            row.append(InlineKeyboardButton(f"{opt}MB", callback_data=str(opt)))
            if len(row) == 3: btns.append(row); row = []
    if row: btns.append(row)
    
    await message.reply_text("🎯 **Target Size select karein:**", reply_markup=InlineKeyboardMarkup(btns))

# --- 3. COMPRESSION & UPLOAD ---
@app.on_callback_query()
async def process_video(client, query):
    uid = query.from_user.id
    data = user_data.get(uid)
    if not data: return

    target_mb = int(query.data)
    out = data['name']
    if "." not in out: out += ".mp4"
    
    msg = await query.message.edit_text("⚙️ **Initializing Engine...**")

    try:
        probe = subprocess.check_output(['./ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', data['path']])
        total_duration = float(probe)
        bitrate = int((target_mb * 8192) / total_duration)

        cmd = f'./ffmpeg -i "{data["path"]}" -b:v {bitrate}k -vcodec libx264 -crf 24 -preset fast "{out}" -y > ffmpeg_log.txt 2>&1'
        process = subprocess.Popen(cmd, shell=True)

        await track_compression(process, msg, total_duration, out)
        process.wait()

        await msg.edit_text("📤 **Compression Done! Uploading...**")
        await client.send_video(
            chat_id=query.message.chat.id, video=out, thumb=data.get("thumb"),
            caption=f"✅ **Done Shakeel Bhai!**\n📂 `{out}`",
            supports_streaming=True,
            progress=progress, progress_args=(msg, "📤 **Uploading...**")
        )
    except Exception as e:
        await msg.edit_text(f"❌ Error: {e}")

    # Cleanup
    if os.path.exists("ffmpeg_log.txt"): os.remove("ffmpeg_log.txt")
    for f in [data['path'], out, data.get("thumb")]:
        if f and os.path.exists(f): os.remove(f)
    user_data.pop(uid, None)

app.run()
