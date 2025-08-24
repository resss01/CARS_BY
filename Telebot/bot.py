import logging
import os
import re
import tempfile
import time
import hashlib
from collections import deque
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import yt_dlp as youtube_dl
import instaloader
from TikTokApi import TikTokApi
import requests
import json
from functools import lru_cache

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Токен вашего бота (получите у @BotFather)
TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"

# Создаем временную директорию для загрузок
DOWNLOAD_DIR = tempfile.mkdtemp()

# Очередь запросов
request_queue = deque()
MAX_QUEUE_SIZE = 10

# Лимиты использования (user_id -> количество запросов и временная метка)
user_limits = {}
MAX_REQUESTS_PER_HOUR = 5

# Кэш для уже скачанных видео (хэш URL -> путь к файлу)
video_cache = {}
CACHE_MAX_SIZE = 50
CACHE_EXPIRY_HOURS = 24

# Блокировка для многопоточного доступа
import threading
lock = threading.Lock()

# Функция для обработки команды /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update.message.reply_text(
        f"Привет! Отправь мне ссылку на видео из Instagram, YouTube или TikTok, и я скачаю его для тебя.\n"
        f"Лимит: {MAX_REQUESTS_PER_HOUR} запросов в час."
    )

# Функция для обработки команды /stats
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    with lock:
        user_stats = user_limits.get(user_id, {"count": 0, "timestamp": datetime.now()})
        await update.message.reply_text(
            f"Ваша статистика:\n"
            f"Запросов в текущем часе: {user_stats['count']}/{MAX_REQUESTS_PER_HOUR}\n"
            f"Размер очереди: {len(request_queue)}\n"
            f"Размер кэша: {len(video_cache)}"
        )

# Функция для проверки лимитов пользователя
def check_user_limit(user_id):
    now = datetime.now()
    with lock:
        if user_id not in user_limits:
            user_limits[user_id] = {"count": 1, "timestamp": now}
            return True
        
        user_data = user_limits[user_id]
        
        # Сброс счетчика, если прошел час
        if now - user_data["timestamp"] > timedelta(hours=1):
            user_data["count"] = 1
            user_data["timestamp"] = now
            return True
        
        # Проверка лимита
        if user_data["count"] < MAX_REQUESTS_PER_HOUR:
            user_data["count"] += 1
            return True
    
    return False

# Функция для получения хэша URL (для кэширования)
def get_url_hash(url):
    return hashlib.md5(url.encode()).hexdigest()

# Функция для проверки кэша
def check_cache(url):
    url_hash = get_url_hash(url)
    if url_hash in video_cache:
        cache_data = video_cache[url_hash]
        # Проверяем, не устарела ли запись в кэше
        if datetime.now() - cache_data["timestamp"] < timedelta(hours=CACHE_EXPIRY_HOURS):
            if os.path.exists(cache_data["file_path"]):
                return cache_data["file_path"]
        else:
            # Удаляем устаревшую запись
            with lock:
                if os.path.exists(cache_data["file_path"]):
                    os.remove(cache_data["file_path"])
                del video_cache[url_hash]
    return None

# Функция для добавления в кэш
def add_to_cache(url, file_path):
    url_hash = get_url_hash(url)
    with lock:
        # Очищаем кэш, если он превысил максимальный размер
        if len(video_cache) >= CACHE_MAX_SIZE:
            # Удаляем самую старую запись
            oldest_key = min(video_cache.keys(), key=lambda k: video_cache[k]["timestamp"])
            if os.path.exists(video_cache[oldest_key]["file_path"]):
                os.remove(video_cache[oldest_key]["file_path"])
            del video_cache[oldest_key]
        
        video_cache[url_hash] = {
            "file_path": file_path,
            "timestamp": datetime.now()
        }

# Функция для загрузки видео с YouTube
async def download_youtube_video(url, update: Update):
    try:
        ydl_opts = {
            'format': 'best[height<=720]',
            'outtmpl': os.path.join(DOWNLOAD_DIR, '%(title)s.%(ext)s'),
            'quiet': True,
            'noplaylist': True,
        }
        
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            file_path = ydl.prepare_filename(info)
            
        return file_path
    except Exception as e:
        await update.message.reply_text(f"Ошибка при загрузке видео с YouTube: {str(e)}")
        logger.error(f"YouTube download error: {str(e)}")
        return None

# Функция для загрузки видео с Instagram
async def download_instagram_video(url, update: Update):
    try:
        L = instaloader.Instaloader(
            dirname_pattern=DOWNLOAD_DIR,
            filename_pattern="{shortcode}",
            download_videos=True,
            download_video_thumbnails=False,
            download_geotags=False,
            download_comments=False,
            save_metadata=False,
            compress_json=False
        )
        
        # Получаем shortcode из URL
        shortcode = re.search(r'instagram\.com/p/([^/]+)', url)
        if not shortcode:
            shortcode = re.search(r'instagram\.com/reel/([^/]+)', url)
        if not shortcode:
            shortcode = re.search(r'instagram\.com/tv/([^/]+)', url)
        
        if shortcode:
            shortcode = shortcode.group(1)
            post = instaloader.Post.from_shortcode(L.context, shortcode)
            
            if post.is_video:
                L.download_post(post, target=DOWNLOAD_DIR)
                # Ищем скачанный файл
                for file in os.listdir(DOWNLOAD_DIR):
                    if file.endswith('.mp4') and shortcode in file:
                        return os.path.join(DOWNLOAD_DIR, file)
            
        await update.message.reply_text("Не удалось найти видео в указанном посте Instagram.")
        return None
    except Exception as e:
        await update.message.reply_text(f"Ошибка при загрузке видео с Instagram: {str(e)}")
        logger.error(f"Instagram download error: {str(e)}")
        return None

# Функция для загрузки видео с TikTok
async def download_tiktok_video(url, update: Update):
    try:
        # Используем бесплатный API для обхода ограничений
        api_url = f"https://api.tiktokv.com/aweme/v1/aweme/detail/?aweme_id={url.split('/')[-1]}"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        response = requests.get(api_url, headers=headers)
        if response.status_code == 200:
            data = response.json()
            video_url = data['aweme_detail']['video']['play_addr']['url_list'][0]
            
            # Скачиваем видео
            video_response = requests.get(video_url, headers=headers, stream=True)
            if video_response.status_code == 200:
                file_path = os.path.join(DOWNLOAD_DIR, f"tiktok_video_{int(time.time())}.mp4")
                with open(file_path, 'wb') as f:
                    for chunk in video_response.iter_content(chunk_size=1024):
                        if chunk:
                            f.write(chunk)
                return file_path
        
        await update.message.reply_text("Не удалось скачать видео с TikTok.")
        return None
    except Exception as e:
        await update.message.reply_text(f"Ошибка при загрузке видео с TikTok: {str(e)}")
        logger.error(f"TikTok download error: {str(e)}")
        return None

# Функция для обработки видео из очереди
async def process_queue():
    while True:
        if request_queue:
            with lock:
                update, context, url, platform = request_queue.popleft()
            
            try:
                # Проверяем кэш
                cached_file = check_cache(url)
                if cached_file:
                    await context.bot.send_video(
                        chat_id=update.effective_chat.id,
                        video=open(cached_file, 'rb'),
                        caption=f"Видео с {platform} (из кэша)"
                    )
                    continue
                
                # Загружаем видео
                if platform == 'YouTube':
                    file_path = await download_youtube_video(url, update)
                elif platform == 'Instagram':
                    file_path = await download_instagram_video(url, update)
                elif platform == 'TikTok':
                    file_path = await download_tiktok_video(url, update)
                
                if file_path and os.path.exists(file_path):
                    # Добавляем в кэш
                    add_to_cache(url, file_path)
                    
                    # Отправляем видео пользователю
                    await context.bot.send_video(
                        chat_id=update.effective_chat.id,
                        video=open(file_path, 'rb'),
                        caption=f"Видео с {platform}"
                    )
                else:
                    await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text="Не удалось скачать видео. Попробуйте другую ссылку."
                    )
            except Exception as e:
                logger.error(f"Error processing video: {str(e)}")
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text="Произошла ошибка при обработке вашего запроса."
                )
        
        # Задержка между обработкой запросов
        time.sleep(2)

# Функция для обработки входящих сообщений
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    message_text = update.message.text
    
    # Проверяем лимиты пользователя
    if not check_user_limit(user_id):
        await update.message.reply_text(
            f"Вы превысили лимит запросов ({MAX_REQUESTS_PER_HOUR} в час). "
            f"Попробуйте позже."
        )
        return
    
    # Проверяем, является ли сообщение URL
    if not re.match(r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+', message_text):
        await update.message.reply_text("Пожалуйста, отправьте действительную ссылку на видео.")
        return
    
    # Определяем платформу по URL
    if 'youtube.com' in message_text or 'youtu.be' in message_text:
        platform = 'YouTube'
    elif 'instagram.com' in message_text:
        platform = 'Instagram'
    elif 'tiktok.com' in message_text:
        platform = 'TikTok'
    else:
        await update.message.reply_text("Поддерживаются только ссылки из YouTube, Instagram и TikTok.")
        return
    
    # Проверяем кэш
    cached_file = check_cache(message_text)
    if cached_file:
        await update.message.reply_video(
            video=open(cached_file, 'rb'),
            caption=f"Видео с {platform} (из кэша)"
        )
        return
    
    # Добавляем в очередь
    with lock:
        if len(request_queue) >= MAX_QUEUE_SIZE:
            await update.message.reply_text(
                "Очередь запросов переполнена. Пожалуйста, попробуйте позже."
            )
            return
        
        request_queue.append((update, context, message_text, platform))
    
    # Сообщаем пользователю о добавлении в очередь
    queue_position = len(request_queue)
    await update.message.reply_text(
        f"Ваш запрос добавлен в очередь. Позиция в очереди: {queue_position}. "
        f"Обработка начнется в ближайшее время."
    )

# Функция для очистки устаревших файлов
def cleanup_old_files():
    while True:
        try:
            now = time.time()
            for filename in os.listdir(DOWNLOAD_DIR):
                file_path = os.path.join(DOWNLOAD_DIR, filename)
                # Удаляем файлы старше 24 часов
                if os.path.isfile(file_path) and now - os.path.getctime(file_path) > 24 * 3600:
                    os.remove(file_path)
        except Exception as e:
            logger.error(f"Error cleaning up files: {str(e)}")
        
        # Очищаем каждые 6 часов
        time.sleep(6 * 3600)

# Основная функция
def main():
    # Создаем приложение и передаем ему токен бота
    application = Application.builder().token(TOKEN).build()
    
    # Добавляем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Запускаем фоновые задачи
    import threading
    queue_thread = threading.Thread(target=lambda: asyncio.run(process_queue()), daemon=True)
    cleanup_thread = threading.Thread(target=cleanup_old_files, daemon=True)
    
    queue_thread.start()
    cleanup_thread.start()
    
    # Запускаем бота
    print("Бот запущен...")
    application.run_polling()

if __name__ == '__main__':
    import asyncio
    main()