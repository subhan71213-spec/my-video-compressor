import os
import subprocess
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# --- CONFIG ---
TOKEN = os.getenv("BOT_TOKEN")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Bhai, video bhejo! Phir main Thumbnail, Rename aur Compress kar dunga.")

async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    video_file = await update.message.video.get_file()
    input_path = "input_video.mp4"
    await video_file.download_to_drive(input_path)
    
    await update.message.reply_text("Video mil gayi! Ab batao kitne MB mein compress karun? (Example: Type 800 for 800MB)")
    context.user_data['file_path'] = input_path

async def process_compression(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target_mb = int(update.message.text)
    input_path = context.user_data.get('file_path')
    output_path = f"compressed_{target_mb}MB.mp4"

    # Get Duration
    probe = f'ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "{input_path}"'
    duration = float(subprocess.check_output(probe, shell=True))

    # Bitrate Calculation
    bitrate = int((target_mb * 8192) / duration)

    await update.message.reply_text(f"⏳ {target_mb}MB mein compress ho raha hai... Time lagega thoda.")

    # FFmpeg Command
    cmd = f'ffmpeg -i "{input_path}" -b:v {bitrate}k -vcodec libx264 -preset fast -acodec aac -b:a 128k "{output_path}" -y'
    subprocess.run(cmd, shell=True)

    # Send Result
    await update.message.reply_video(video=open(output_path, 'rb'), caption=f"Done! Compressed to {target_mb}MB")
    
    # Cleanup
    os.remove(input_path)
    os.remove(output_path)

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.VIDEO, handle_video))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, process_compression))
    app.run_polling()

if __name__ == '__main__':
    main()
  
