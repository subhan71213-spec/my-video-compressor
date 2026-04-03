import os
import subprocess
import asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")

app = Client("VideoCompressorBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
user_data = {}

# --- PROGRESS BAR ---
async def progress(current, total, message, text):
    try:
        percent = current * 100 / total
        if int(percent) % 15 == 0 or percent > 95:
            bar = "▓" * int(percent/10) + "░" * (10 - int(percent/10))
            await message.edit_text(f"{text}\n\n{bar} {round(percent, 2)}%")
    except:
        pass

# --- TRACK COMPRESSION ---
async def track_compression(process, message, total_duration, out_file, stage=""):
    last_size = 0
    while process.poll() is None:
        try:
            if os.path.exists(out_file):
                current_size = os.path.getsize(out_file) / (1024 * 1024)
                if current_size > last_size + 1.5:
                    percent = min(98, int((current_size / max(80, current_size * 1.4)) * 100))
                    text = f"🚀 {stage} Compressing: {percent}%\n📦 Size: {round(current_size, 2)} MB"
                    await message.edit_text(text)
                    last_size = current_size
        except:
            pass
        await asyncio.sleep(5)

    try:
        final_size = os.path.getsize(out_file) / (1024 * 1024) if os.path.exists(out_file) else 0
        await message.edit_text(f"✅ {stage} Finished!\n📦 Final Size: {round(final_size, 2)} MB")
    except:
        pass

# --- START ---
@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    await message.reply_text("👋 Hi Shakeel!\nSend a video to begin. 🚀")

# --- RECEIVE VIDEO ---
@app.on_message(filters.private & (filters.video | filters.document))
async def handle_video(client, message):
    uid = message.from_user.id
    if uid in user_data:
        await cleanup_user_data(uid)
    
    msg = await message.reply_text("📥 Downloading...")
    path = await client.download_media(message, progress=progress, progress_args=(msg, "📥 Downloading..."))
    
    user_data[uid] = {"path": path, "stage": "name"}
    await msg.edit_text("✅ Downloaded!\n\n📂 Send the **New File Name** (No extension needed):")

# --- RENAME HANDLER ---
@app.on_message(filters.private & filters.text)
async def get_name(client, message):
    if message.text.startswith("/"):
        return
    uid = message.from_user.id
    if uid in user_data and user_data[uid].get("stage") == "name":
        user_data[uid]["raw_name"] = message.text.strip()
        user_data[uid]["stage"] = "thumb"
        await message.reply_text("🖼 Send a thumbnail photo or /skip")

# --- THUMBNAIL ---
@app.on_message(filters.private & (filters.photo | filters.command("skip")))
async def get_thumb(client, message):
    uid = message.from_user.id
    if uid not in user_data or user_data[uid].get("stage") != "thumb":
        return

    if message.photo:
        user_data[uid]["thumb"] = await client.download_media(message.photo)
    else:
        user_data[uid]["thumb"] = None

    size = os.path.getsize(user_data[uid]["path"]) / (1024 * 1024)
    
    if size >= 1400:
        btns = [[InlineKeyboardButton("🔥 1500MB", callback_data="1500"), 
                 InlineKeyboardButton("🔥 1000MB", callback_data="1000")]]
    elif size >= 900:
        btns = [[InlineKeyboardButton("⚖️ 800MB", callback_data="800"), 
                 InlineKeyboardButton("⚖️ 600MB", callback_data="600")]]
    elif size >= 500:
        btns = [[InlineKeyboardButton("📦 800MB", callback_data="800"), 
                 InlineKeyboardButton("📦 600MB", callback_data="600")]]
    else:
        btns = [[InlineKeyboardButton("📦 600MB", callback_data="600"), 
                 InlineKeyboardButton("📦 400MB", callback_data="400")]]

    await message.reply_text(f"📏 Current Size: {round(size, 2)} MB\n\n🎯 Select Target Size:", 
                             reply_markup=InlineKeyboardMarkup(btns))
    user_data[uid]["stage"] = "compress"

# --- CLEANUP ---
async def cleanup_user_data(uid):
    data = user_data.get(uid, {})
    for file in [data.get('path'), data.get("thumb")]:
        if file and os.path.exists(file):
            try: os.remove(file)
            except: pass
    user_data.pop(uid, None)

# --- CORE COMPRESSION (Playable + Fast Start + Telegram Safe) ---
@app.on_callback_query()
async def process_video(client, query):
    uid = query.from_user.id
    data = user_data.get(uid)
    if not data or data.get("stage") != "compress":
        await query.answer("Session expired. Send video again.", show_alert=True)
        return

    target_mb = int(query.data)
    base_name = data.get("raw_name", "video")

    out_720 = f"{base_name}_720p.mp4"
    out_480 = f"{base_name}_480p.mp4"
    out_360 = f"{base_name}_360p.mp4"

    msg = await query.message.edit_text(f"⚙️ Starting compression...\n🎯 Target: \~{target_mb}MB\n🔧 Making sure file is playable...")

    try:
        fp_cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", data['path']]
        duration = float(subprocess.check_output(fp_cmd).decode().strip() or 0)

        if duration <= 0:
            await msg.edit_text("❌ Could not get video duration!")
            await cleanup_user_data(uid)
            return

        # Special for 1500MB (bigger size)
        if target_mb == 1500:
            factor = 0.92
            crf_720, crf_480, crf_360 = 22, 23, 24
        else:
            factor = 0.88
            crf_720, crf_480, crf_360 = 23, 24, 25

        target_bytes = target_mb * 1024 * 1024
        video_bits = (target_bytes * 8 * factor) / duration
        base_bitrate = int(video_bits / 1000)

        # Common safe flags for all qualities
        common_out = '-pix_fmt yuv420p -movflags +faststart -flags +global_header -profile:v baseline -level 3.0'

        # 720p
        await msg.edit_text("🔄 Encoding 720p (Playable mode)...")
        cmd_720 = f'ffmpeg -i "{data["path"]}" -vf "scale=1280:-2" -c:v libx264 -preset veryfast -crf {crf_720} -b:v {int(base_bitrate*1.75)}k -maxrate {int(base_bitrate*2.3)}k -bufsize {int(base_bitrate*7)}k {common_out} -c:a aac -b:a 128k -ac 2 -threads 2 "{out_720}" -y'
        process = subprocess.Popen(cmd_720, shell=True)
        await track_compression(process, msg, duration, out_720, "720p")
        process.wait()

        # 480p
        await msg.edit_text("🔄 Encoding 480p (Playable mode)...")
        cmd_480 = f'ffmpeg -i "{data["path"]}" -vf "scale=854:-2" -c:v libx264 -preset veryfast -crf {crf_480} -b:v {int(base_bitrate*1.05)}k -maxrate {int(base_bitrate*1.4)}k -bufsize {int(base_bitrate*5)}k {common_out} -c:a aac -b:a 96k -ac 2 -threads 2 "{out_480}" -y'
        process = subprocess.Popen(cmd_480, shell=True)
        await track_compression(process, msg, duration, out_480, "480p")
        process.wait()

        # 360p
        await msg.edit_text("🔄 Encoding 360p (Playable mode)...")
        cmd_360 = f'ffmpeg -i "{data["path"]}" -vf "scale=640:-2" -c:v libx264 -preset veryfast -crf {crf_360} -b:v {int(base_bitrate*0.78)}k -maxrate {int(base_bitrate*1.0)}k -bufsize {int(base_bitrate*4)}k {common_out} -c:a aac -b:a 64k -ac 2 -threads 2 "{out_360}" -y'
        process = subprocess.Popen(cmd_360, shell=True)
        await track_compression(process, msg, duration, out_360, "360p")
        process.wait()

        # Upload
        await msg.edit_text("📤 Uploading playable files...")
        files = [
            (out_720, "720p", f"{base_name} 720p.mp4"),
            (out_480, "480p", f"{base_name} 480p.mp4"),
            (out_360, "360p", f"{base_name} 360p.mp4")
        ]
        
        for out_file, res, clean_name in files:
            if os.path.exists(out_file) and os.path.getsize(out_file) > 50000:
                final_size = os.path.getsize(out_file) / (1024 * 1024)
                await client.send_video(
                    chat_id=query.message.chat.id,
                    video=out_file,
                    duration=int(duration),
                    thumb=data.get("thumb"),
                    file_name=clean_name,
                    caption=f"✅ {res}\n📂 {base_name}\n📊 Size: {round(final_size, 2)} MB",
                    supports_streaming=True,
                    progress=progress,
                    progress_args=(msg, f"📤 Uploading {res}...")
                )

        await msg.edit_text("✅ All 3 qualities uploaded successfully! Files should play properly now.")

    except Exception as e:
        await msg.edit_text(f"❌ Error: {str(e)}")

    finally:
        await cleanup_user_data(uid)
        for f in [out_720, out_480, out_360]:
            if os.path.exists(f):
                try: os.remove(f)
                except: pass

# --- RUN ---
if __name__ == "__main__":
    print("Bot Started Successfully!")
    app.run()
