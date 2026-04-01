# Python image use karein
FROM python:3.10-slim

# FFmpeg aur FFprobe install karne ke liye
RUN apt-get update && apt-get install -y ffmpeg

# Work directory set karein
WORKDIR /app

# Requirements copy aur install karein
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Baaki saara code copy karein
COPY . .

# Bot start karne ki command
CMD ["python", "main.py"]
