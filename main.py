import os
import subprocess
import asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# --- CONFIG ---
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")

app = Client("my_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Temporary storage for user data
user_data = {}

@app.on_message(filters.command("start"))
async def start(client, message):
    await message.reply_text("👋 Bhai, 2GB tak ki koi bhi video bhejo. Main compress kar dunga!")

@app.on_message(filters.video | filters.document)
async def handle_video(client, message):
    file_id = message.video.file_id if message.video else message.document.file_id
    file_name = message.video.file_name if message.video else message.document.file_name
    
    msg = await message.reply_text("📥 Video download ho rahi hai... Sabar rakho.")
    
    # Download file
    input_path = await client.download_media(message, file_name=file_name)
    user_data[message.from_user.id] = {"path": input_path, "name": file_name}
    
    # Options Buttons
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("Compress to 1300MB", callback_data="1300")],
        [InlineKeyboardButton("Compress to 800MB", callback_data="800")],
        [InlineKeyboardButton("Compress to 400MB", callback_data="400")]
    ])
    
    await msg.edit_text(f"✅ Video mil gayi: {file_name}\nAb size select karo:", reply_markup=buttons)

@app.on_callback_query()
async def callback_handler(client, callback_query):
    user_id = callback_query.from_user.id
    target_mb = int(callback_query.data)
    data = user_data.get(user_id)
    
    if not data:
        await callback_query.answer("Error: File not found!", show_alert=True)
        return

    input_path = data["path"]
    output_path = f"compressed_{target_mb}mb_{data['name']}"
    thumb_path = f"thumb_{user_id}.jpg"

    await callback_query.message.edit_text(f"⏳ {target_mb}MB mein conversion start ho gaya hai...")

    # 1. Thumbnail nikalna (5th second se)
    subprocess.run(f'ffmpeg -i "{input_path}" -ss 00:00:05 -vframes 1 "{thumb_path}" -y', shell=True)

    # 2. Compression Logic
    probe = subprocess.check_output(f'ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "{input_path}"', shell=True)
    duration = float(probe)
    bitrate = int((target_mb * 8192) / duration)

    # FFmpeg Command
    cmd = f'ffmpeg -i "{input_path}" -b:v {bitrate}k -vcodec libx264 -preset ultrafast -acodec aac -b:a 128k "{output_path}" -y'
    subprocess.run(cmd, shell=True)

    # 3. Uploading back to Telegram
    await callback_query.message.edit_text("📤 Compression done! Ab upload ho raha hai...")
    await client.send_video(
        chat_id=callback_query.message.chat.id,
        video=output_path,
        thumb=thumb_path,
        caption=f"✅ Compressed to {target_mb}MB\nOriginal: {data['name']}",
        supports_streaming=True
    )

    # Cleanup
    if os.path.exists(input_path): os.remove(input_path)
    if os.path.exists(output_path): os.remove(output_path)
    if os.path.exists(thumb_path): os.remove(thumb_path)

app.run()
