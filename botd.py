import os
import threading
import queue
import time
import asyncio
from yt_dlp import YoutubeDL
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# متغيرات التحكم
is_paused = False
stop_download = False
download_queue = queue.Queue()  # قائمة انتظار للتحميل
current_download = None  # الملف الذي يتم تحميله حالياً
download_progress = {}  # لتخزين حالة التحميل لكل مستخدم

# وظيفة تحميل الفيديو
def download_video(url, output_path='.', filename=None):
    global is_paused, stop_download, current_download, download_progress

    try:
        ydl_opts = {
            'outtmpl': f'{output_path}/{filename}.%(ext)s' if filename else f'{output_path}/%(title)s.%(ext)s',
            'format': 'best',  # أفضل تنسيق متاح
            'noprogress': True,  # إخفاء شريط التقدم الافتراضي
            'continuedl': True,  # تمكين استئناف التحميل
        }

        def progress_hook(d):
            global is_paused, stop_download
            if d['status'] == 'downloading':
                while is_paused:  # انتظار حتى يتم استئناف التحميل
                    time.sleep(1)
                if stop_download:  # إيقاف التحميل إذا طُلب ذلك
                    raise Exception("Download stopped by user.")

                # حفظ تفاصيل التقدم
                percent = d.get('_percent_str', 'N/A').strip()  # النسبة المئوية
                speed = d.get('_speed_str', 'N/A').strip()  # السرعة
                eta = d.get('_eta_str', 'N/A').strip()  # الوقت المتبقي
                total_size = d.get('_total_bytes_str', 'N/A').strip()  # الحجم الكلي للفيديو
                download_progress[current_download] = {
                    'percent': percent,
                    'speed': speed,
                    'eta': eta,
                    'total_size': total_size
                }

        ydl_opts['progress_hooks'] = [progress_hook]

        with YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            return info_dict['title'], ydl.prepare_filename(info_dict)
    except Exception as e:
        print(f"\nAn error occurred: {e}")
        return None, None
    finally:
        current_download = None  # إعادة تعيين الملف الحالي بعد الانتهاء

# وظيفة معالجة قائمة الانتظار
async def process_queue():
    global current_download
    while True:
        item = download_queue.get()
        if item is None:
            break
        url, update, context = item
        current_download = url  # تعيين الملف الحالي
        title, file_path = await asyncio.to_thread(download_video, url)
        if title and file_path:
            try:
                await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Download complete: {title}")
                with open(file_path, 'rb') as video_file:
                    await context.bot.send_video(
                        chat_id=update.effective_chat.id,
                        video=video_file,
                        read_timeout=60,  # زيادة المهلة إلى 60 ثانية
                        write_timeout=60  # زيادة المهلة إلى 60 ثانية
                    )
            except Exception as e:
                await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Failed to send video: {e}")
            finally:
                os.remove(file_path)  # حذف الملف بعد الإرسال
        else:
            await context.bot.send_message(chat_id=update.effective_chat.id, text="Failed to download the video.")
        download_queue.task_done()

# وظيفة بدء البوت
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Welcome! Send me a video URL to download.")

# وظيفة معالجة الرسائل
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text
    download_queue.put((url, update, context))
    await update.message.reply_text("Your download has been added to the queue. Please wait.")

# وظيفة الإيقاف المؤقت
async def pause(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global is_paused
    is_paused = True
    await update.message.reply_text("Download paused.")

# وظيفة الاستئناف
async def resume(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global is_paused
    is_paused = False
    await update.message.reply_text("Download resumed.")

# وظيفة إلغاء التحميل
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global stop_download, current_download
    if current_download:
        stop_download = True
        await update.message.reply_text("Download cancelled.")
    else:
        await update.message.reply_text("No active download to cancel.")

# وظيفة عرض حالة التحميل
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global download_progress, current_download
    if current_download and current_download in download_progress:
        progress = download_progress[current_download]
        await update.message.reply_text(
            f"Download Status:\n"
            f"Progress: {progress['percent']}\n"
            f"Speed: {progress['speed']}\n"
            f"ETA: {progress['eta']}\n"
            f"Size: {progress['total_size']}"
        )
    else:
        await update.message.reply_text("No active download.")

# تشغيل البوت
async def main():
    # استخدام التوكن مباشرة (لأغراض الاختبار فقط)
    TOKEN = "7336372322:AAEtIUcY6nNEEGZzIMjJdfYMTAMsLpTSpzk"
    application = Application.builder().token(TOKEN).build()

    # إضافة معالجات الأوامر والرسائل
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("pause", pause))
    application.add_handler(CommandHandler("resume", resume))
    application.add_handler(CommandHandler("cancel", cancel))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # بدء معالجة قائمة الانتظار في خيط منفصل
    threading.Thread(target=lambda: asyncio.run(process_queue()), daemon=True).start()

    # بدء البوت
    await application.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
