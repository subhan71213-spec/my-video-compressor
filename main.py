import os
import subprocess
import asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from pyrogram.errors import FloodWait

# --- CONFIG ---
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")

app = Client("InteractiveCompressor", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# User states storage
user_data = {}

async def progress(current, total, message, text):
    try:
        percent = current * 100 / total
        bar = "▓" * int(percent/10) + "░" * (10 - int(percent/10))
        await message.edit_text(f"{text}\n\n{bar} {round(percent, 2)}%")
    except: pass

@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    await message.reply_text("👋 **Hi Shakeel!**\nVideo bhejein, main Rename aur Thumbnail dono puchunga.")

@app.on_message(filters.private & (filters.video | filters.document))
async def handle_video(client, message):
    file = message.video or message.document
    if not file: return
    
    file_name = file.file_name or "video.mp4"
    file_size_mb = file.file_size / (1024 * 1024)
    
    msg = await message.reply_text("📥 **Downloading...**")
    path = await client.download_media(message, progress=progress, progress_args=(msg, "📥 **Downloading...**"))
    
    # Save data and ask for Rename
    user_data[message.from_user.id] = {"path": path, "original_name": file_name, "size": file_size_mb, "msg_id": msg.id}
    
    await msg.edit_text(f"✅ Downloaded!\n\n📂 **Ab Naya Naam (Rename) bhejein:**\n(Example: MyMovie.mp4)")

@app.on_message(filters.private & filters.text & ~filters.command("start"))
async def get_name(client, message):
    user_id = message.from_user.id
    if user_id in user_data and "new_name" not in user_data[user_id]:
        user_data[user_id]["new_name"] = message.text
        await message.reply_text("🖼️ **Ab Thumbnail (Photo) bhejein:**\n(Agar thumbnail nahi chahiye to /skip likhein)")
        return

@app.on_message(filters.private & (filters.photo | filters.command("skip")))
async def get_thumbnail(client, message):
    user_id = message.from_user.id
    if user_id in user_data and "new_name" in user_data[user_id]:
        if message.photo:
            thumb_path = await client.download_media(message.photo)
            user_data[user_id]["thumb"] = thumb_path
        else:
            user_data[user_id]["thumb"] = None
            
        # Ab Buttons dikhao Size select karne ke liye
        file_size = user_data[user_id]["size"]
        options = [1500, 1000, 700, 500, 400, 300, 200, 100]
        buttons = []
        row = []
        for opt in options:
            if opt < file_size:
                row.append(InlineKeyboardButton(f"{opt}MB", callback_data=str(opt)))
                if len(row) == 3:
                    buttons.append(row); row = []
        if row: buttons.append(row)
        
        await message.reply_text("🎯 **Target Size select karein:**", reply_markup=InlineKeyboardMarkup(buttons))

@app.on_callback_query()
async def compress_now(client, query):
    user_id = query.from_user.id
    target_mb = int(query.data)
    data = user_data.get(user_id)
    
    if not data: return

    input_path = data['path']
    output_path = data['new_name']
    if not output_path.endswith(('.mp4', '.mkv')): output_path += ".mp4"
    
    thumb_path = data.get("thumb")
    
    await query.message.edit_text(f"⚙️ **Compressing to {target_mb}MB...**")

    try:
        # Get duration for bitrate
        probe = subprocess.check_output(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', input_path])
        duration = float(probe)
        bitrate = int((target_mb * 8192) / duration)

        # Compress
        cmd = f'ffmpeg -i "{input_path}" -b:v {bitrate}k -vcodec libx264 -crf 24 -preset fast "{output_path}" -y'
        subprocess.run(cmd, shell=True)

        await query.message.edit_text("📤 **Uploading...**")
        
        await client.send_video(
            chat_id=query.message.chat.id,
            video=output_path,
            thumb=thumb_path,
            caption=f"✅ **Done!**\n📂 `{output_path}`",
            progress=progress,
            progress_args=(query.message, "📤 **Uploading...**")
        )
    except Exception as e:
        await query.message.edit_text(f"❌ Error: {e}")

    # Cleanup
    for f in [input_path, output_path, thumb_path]:
        if f and os.path.exists(f): os.remove(f)
    del user_data[user_id]

app.run()
