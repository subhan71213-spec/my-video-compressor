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
user_data = {}

# Progress Bar Function
async def progress_bar(current, total, message, text):
    try:
        percent = current * 100 / total
        completed = int(percent / 10)
        bar = "▓" * completed + "░" * (10 - completed)
        tmp = f"{text}\n\n{bar} {round(percent, 2)}%"
        await message.edit_text(tmp)
    except:
        pass

@app.on_message(filters.private & (filters.video | filters.document))
async def handle_video(client, message):
    file = message.video or message.document
    if not file: return
    
    file_size_mb = file.file_size / (1024 * 1024)
    file_name = file.file_name or "video.mp4"
    
    msg = await message.reply_text("📥 Downloading starts...")

    # Download
    input_path = await client.download_media(
        message, 
        progress=progress_bar,
        progress_args=(msg, "📥 Downloading your video...")
    )
    
    user_data[message.from_user.id] = {"path": input_path, "name": file_name, "size": file_size_mb}

    options = [1900, 1700, 1500, 1300, 1100, 900, 700, 500, 400, 300, 200, 100]
    buttons = []
    row = []
    for opt in options:
        if opt < file_size_mb:
            row.append(InlineKeyboardButton(f"{opt}MB", callback_data=str(opt)))
            if len(row) == 3:
                buttons.append(row)
                row = []
    
    if row: buttons.append(row)

    # अगर कोई बटन नहीं बना (छोटी वीडियो के लिए)
    if not buttons:
        buttons.append([
            InlineKeyboardButton("Compress 50%", callback_data=str(int(file_size_mb/2))),
            InlineKeyboardButton("Compress 75%", callback_data=str(int(file_size_mb/4)))
        ])

    await msg.edit_text(
        f"✅ Downloaded: {file_name}\nSize: {round(file_size_mb, 2)} MB\n\nAb target size select karo:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )


@app.on_callback_query()
async def callback_handler(client, callback_query):
    user_id = callback_query.from_user.id
    target_mb = int(callback_query.data)
    data = user_data.get(user_id)

    if not data:
        await callback_query.answer("Error: File not found!", show_alert=True)
        return

    input_path = data['path']
    
    # 1. FILE RENAME: Naya naam set karna
    new_name = f"Compressed_{target_mb}MB_{data['name']}"
    output_path = os.path.join(os.getcwd(), new_name)
    thumb_path = f"thumb_{user_id}.jpg"
    
    await callback_query.message.edit_text(f"⚙️ {target_mb}MB mein compress ho raha hai...\nSabar rakhein, isme time lagta hai.")

    try:
        # 2. THUMBNAIL: Video ke 5th second se thumbnail nikalna
        subprocess.run(f'ffmpeg -i "{input_path}" -ss 00:00:05 -vframes 1 "{thumb_path}" -y', shell=True)

        # Get duration
        probe = subprocess.check_output(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', input_path])
        duration = float(probe)
        bitrate = int((target_mb * 8192) / duration)
        
        # 3. COMPRESSION: Achi quality ke liye settings
        cmd = f'ffmpeg -i "{input_path}" -b:v {bitrate}k -vcodec libx264 -crf 24 -preset fast "{output_path}" -y'
        subprocess.run(cmd, shell=True)

        await callback_query.message.edit_text("📤 Compression complete! Ab upload ho raha hai...")
        
        # 4. UPLOAD: Thumbnail aur Naye Naam ke sath
        await client.send_video(
            chat_id=callback_query.message.chat.id,
            video=output_path,
            thumb=thumb_path if os.path.exists(thumb_path) else None,
            caption=f"✅ **File Re-named & Compressed**\n\n📂 Name: `{new_name}`\n🎯 Target: {target_mb}MB",
            supports_streaming=True,
            progress=progress_bar,
            progress_args=(callback_query.message, "📤 Uploading to Telegram...")
        )

    except Exception as e:
        await callback_query.message.edit_text(f"❌ Error: {str(e)}")

    # Cleanup: Sab delete kar do taaki storage full na ho
    for f in [input_path, output_path, thumb_path]:
        if os.path.exists(f): os.remove(f)

app.run()
