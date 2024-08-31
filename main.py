import logging
import re
import os
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, CallbackContext, MessageHandler, filters
import requests
from datetime import datetime, timedelta
from config import TOKEN, CHANNEL_ID, GROUP_ID, ALLOWED_USER_ID
from tags import tags
from banned import banned_tags
import random
import time
import asyncio
import schedule
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# Встановити логування
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Функція для перевірки доступності зображення
def is_image_accessible(url):
    try:
        response = requests.head(url)
        return response.status_code == 200
    except requests.RequestException:
        return False

# Функція для отримання випадкового зображення з Danbooru з врахуванням всіх тегів
def get_random_image():
    random_tag = random.choice(tags)
    url = f"https://danbooru.donmai.us/posts.json?tags={random_tag}&random=true"
    
    for _ in range(10):  # Максимум 10 спроб знайти зображення без забанених тегів
        response = requests.get(url)
        data = response.json()
        
        if isinstance(data, list) and data:
            random.shuffle(data)  # Перемішати результати для додаткової випадковості
            
            for image_data in data:
                image_url = image_data.get('file_url')
                tag_string = image_data.get('tag_string', '')
                rating = image_data.get('rating', '')

                # Перевірити, чи містить тег забанені теги
                if any(banned_tag in tag_string for banned_tag in banned_tags):
                    continue

                if rating == 'g' or rating == 'e':
                    continue

                if is_image_accessible(image_url):
                    published_at = image_data.get('created_at')
                    tag_string_character = image_data.get('tag_string_character', '')
                    characters = tag_string_character.replace(' ', ', ')
                    copyright_info = image_data.get('tag_string_copyright', '')
                    rating = image_data.get('rating', '')
                    tag_string_general = image_data.get('tag_string_general', '')
                    post_id = image_data.get('id')
                    artist = image_data.get('tag_string_artist', '')
                    return image_url, published_at, characters, copyright_info, rating, tag_string_general, post_id, artist

    return None, None, None, None, None, None, None, None

# Функція для очищення імен персонажів
def clean_character_name(name):
    return re.sub(r'_?\([^)]*\)', '', name)

# Оновлення файлу tags.py
def update_tags_file():
    with open("tags.py", "w") as file:
        file.write("tags = [\n")
        for tag in tags:
            file.write(f'    "{tag}",\n')
        file.write("]\n")

# Функція для оновлення файлу banned.py
def update_banned_tags_file():
    with open('banned.py', 'w') as file:
        file.write('banned_tags = [\n')
        for tag in banned_tags:
            file.write(f'    "{tag}",\n')
        file.write(']\n')

# Функція для видалення повідомлення через затримку
async def delete_message_later(context: CallbackContext, message_id: int, chat_id: int, delay: int = 1):
    await asyncio.sleep(delay)
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception as e:
        logger.error(f"Error deleting message: {e}")

# Перевірка дозволу доступу
def is_user_allowed(update: Update) -> bool:
    return update.effective_user.id == ALLOWED_USER_ID

# Команда /start
async def start(update: Update, context: CallbackContext) -> None:
    if not is_user_allowed(update):
        return
    await update.message.reply_text('Вітаю! Надішліть команду /get_image для отримання випадкового зображення.\n'
                                    'Для додавання тегу використайте команду /add_tag <tag>.\n'
                                    'Для видалення тегу використайте команду /remove_tag <tag>.\n'
                                    'Для перегляду всіх тегів використайте команду /list_tags.')
    
# Функція для публікації зображення
async def publish_image(application: Application) -> None:
    image_url, published_at, characters, copyright_info, rating, tag_string_general, post_id, artist = get_random_image()
    if image_url:
        cleaned_characters = {clean_character_name(char) for char in characters.split(', ')}
        character_hashtags = ' '.join(f"#{char}" for char in cleaned_characters)
        
        cleaned_copyrights = {clean_character_name(copyright) for copyright in copyright_info.split(' ')}
        copyright_hashtags = ' '.join(f"#{copyright}" for copyright in cleaned_copyrights)

        if rating == 'g':
            rating = '🟢  •  #general'
        elif rating == 's':
            rating = '🟡  •  #sensitive'
        elif rating == 'q':
            rating = '🟠  •  #questionable'
        elif rating == 'e':
            rating = '🔴  •  #explicit'
        
        hashtags = character_hashtags + '\nКоп: ' + copyright_hashtags
        channel_hashtags = '🎭  •  ' + character_hashtags + '\n' + '🌐  •  ' + copyright_hashtags + '\n🪶  •  #' + artist
        
        post_url = f"https://danbooru.donmai.us/posts/{post_id}"
        re.sub(r'_?\([^)]*\)', '', artist)

        caption = (
            f"Час: {datetime.fromisoformat(published_at).strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"Арт: #{artist}\n"
            f"Перс: {hashtags if hashtags else 'Немає тегів'}\n"
            f"Рейт: {rating}\n"
            f"{post_url}"
        )
        channel_caption = (
            f"{channel_hashtags if channel_hashtags else 'Немає тегів'}"
        )

        try:
            await application.bot.send_photo(chat_id=CHANNEL_ID, photo=image_url, caption=channel_caption)
            logger.info("Image published successfully")
        except Exception as e:
            logger.error(f"Failed to send photo: {e}")
    else:
        logger.error('Failed to get image')

    # Schedule the next job
    schedule_next_job(application)

# Функція для планування наступного запуску
def schedule_next_job(application: Application) -> None:
    scheduler = application.job_queue.scheduler
    # Вибираємо випадкову хвилину
    random_minute = random.randint(0, 59)
    now = datetime.now()
    next_run_time = (now + timedelta(hours=1)).replace(minute=random_minute, second=0, microsecond=0)
    logger.info(f"Next image will be published at {next_run_time.strftime('%Y-%m-%d %H:%M:%S')}")
    scheduler.add_job(publish_image, 'date', run_date=next_run_time, args=(application,))

# Налаштування планувальника
def start_scheduler(application: Application) -> None:
    scheduler = AsyncIOScheduler()
    application.job_queue.scheduler = scheduler
    scheduler.start()
    # Плануємо перший запуск
    schedule_next_job(application)

# Команда /get_image
async def get_image(update: Update, context: CallbackContext) -> None:
    if not is_user_allowed(update):
        return
    image_url, published_at, characters, copyright_info, rating, tag_string_general, post_id, artist = get_random_image()
    if image_url:
        keyboard = [
            [InlineKeyboardButton("Підтвердити", callback_data='confirm')],
            [InlineKeyboardButton("Відхилити", callback_data='reject')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        cleaned_characters = {clean_character_name(char) for char in characters.split(', ')}
        character_hashtags = ' '.join(f"#{char}" for char in cleaned_characters)
        
        cleaned_copyrights = {clean_character_name(copyright) for copyright in copyright_info.split(' ')}
        copyright_hashtags = ' '.join(f"#{copyright}" for copyright in cleaned_copyrights)

        if rating == 'g':
            rating = '🟢  •  #general'
        elif rating == 's':
            rating = '🟡  •  #sensetive'
        elif rating == 'q':
            rating = '🟠  •  #questionable'
        elif rating == 'e':
            rating = '🔴  •  #explicit'
        
        hashtags = character_hashtags + '\nКоп: ' + copyright_hashtags
        channel_hashtags = '🎭  •  ' + character_hashtags + '\n' + '🌐  •  ' + copyright_hashtags + '\n🪶  •  #' + artist
        #  '\n' + rating + 
        
        post_url = f"https://danbooru.donmai.us/posts/{post_id}"

        re.sub(r'_?\([^)]*\)', '', artist)

        caption = (
            f"Час: {datetime.fromisoformat(published_at).strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"Арт: #{artist}\n"
            f"Перс: {hashtags if hashtags else 'Немає тегів'}\n"
            f"Рейт: {rating}\n"
            f"{post_url}"
            
        )
        channel_caption = (
            f"{channel_hashtags if channel_hashtags else 'Немає тегів'}"
        )
        channel_caption = (
            f"{channel_hashtags if channel_hashtags else 'Немає тегів'}"
        )
        
        context.user_data['current_image'] = image_url
        context.user_data['current_caption'] = caption
        context.user_data['current_channel_caption'] = channel_caption
        await update.message.reply_photo(photo=image_url, caption=caption, reply_markup=reply_markup)
    else:
        await update.message.reply_text('Не вдалося отримати зображення. Спробуйте ще раз.')

# Обробка натискання кнопок
async def button(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()
    if query.data == 'confirm':
        image_url = context.user_data.get('current_image')
        caption = context.user_data.get('current_caption')
        channel_caption = context.user_data.get('current_channel_caption')
        if image_url:
            try:
                await context.bot.send_photo(chat_id=CHANNEL_ID, photo=image_url, caption=channel_caption)
                try:
                    keyboard = [
                        [InlineKeyboardButton(f"Опублікувано!", callback_data='reject')]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    await query.edit_message_reply_markup(reply_markup=reply_markup)
                    time.sleep(1)
                    keyboard = [
                        [InlineKeyboardButton("Підтвердити", callback_data='confirm')],
                        [InlineKeyboardButton("Відхилити", callback_data='reject')]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    await query.edit_message_reply_markup(reply_markup=reply_markup)
                except Exception as e:
                    logger.error(f"Failed to edit message text: {e}")
            except Exception as e:
                logger.error(f"Failed to send photo: {e}")
                try:
                    await query.edit_message_text(text="Не вдалося опублікувати зображення.")
                except Exception as e:
                    logger.error(f"Failed to edit message text: {e}")
    elif query.data == 'reject':
        max_retries = 5
        for attempt in range(max_retries):
            image_url, published_at, characters, copyright_info, rating, tag_string_general, post_id, artist = get_random_image()
            if image_url:
                keyboard = [
                    [InlineKeyboardButton("Підтвердити", callback_data='confirm')],
                    [InlineKeyboardButton("Відхилити", callback_data='reject')]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                cleaned_characters = {clean_character_name(char) for char in characters.split(', ')}
                character_hashtags = ' '.join(f"#{char}" for char in cleaned_characters)
                
                cleaned_copyrights = {clean_character_name(copyright) for copyright in copyright_info.split(' ')}
                copyright_hashtags = ' '.join(f"#{copyright}" for copyright in cleaned_copyrights)

                if rating == 'g':
                    rating = '🟢  •  #general'
                elif rating == 's':
                    rating = '🟡  •  #sensetive'
                elif rating == 'q':
                    rating = '🟠  •  #questioable'
                elif rating == 'e':
                    rating = '🔴  •  #explicit'
                
                hashtags = character_hashtags + '\nКоп: ' + copyright_hashtags
                channel_hashtags = '🎭  •  ' + character_hashtags + '\n' + '🌐  •  ' + copyright_hashtags + '\n🪶  •  #' + artist
                # '\n' + rating + 
                
                post_url = f"https://danbooru.donmai.us/posts/{post_id}"

                re.sub(r'_?\([^)]*\)', '', artist)

                caption = (
                    f"Час: {datetime.fromisoformat(published_at).strftime('%Y-%m-%d %H:%M:%S')}\n"
                    f"Арт: #{artist}\n"
                    f"Перс: {hashtags if hashtags else 'Немає тегів'}\n"
                    f"Рейт: {rating}\n"
                    f"{post_url}"
                )
                channel_caption = (
                    f"{channel_hashtags if channel_hashtags else 'Немає тегів'}"
                )
                
                context.user_data['current_image'] = image_url
                context.user_data['current_caption'] = caption
                context.user_data['current_channel_caption'] = channel_caption
                try:
                    await query.edit_message_media(media=InputMediaPhoto(image_url, caption=caption), reply_markup=reply_markup)
                    break
                except Exception as e:
                    logger.error(f"Failed to edit message media (attempt {attempt+1}/{max_retries}): {e}")
                    keyboard = [
                        [InlineKeyboardButton(f"Невдача!\nПочекайте! ({attempt+1}/{max_retries})", callback_data='wait')]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    try:
                        await query.edit_message_reply_markup(reply_markup=reply_markup)
                    except Exception as e:
                        logger.error(f"Failed to edit message reply markup (attempt {attempt+1}/{max_retries}): {e}")
                        keyboard = [
                            [InlineKeyboardButton(f"Невдача!\nПочекайте! ({attempt+1}/{max_retries})", callback_data='wait')]
                        ]
                        reply_markup = InlineKeyboardMarkup(keyboard)
                        await query.edit_message_reply_markup(reply_markup=reply_markup)
                      
                    time.sleep(1)
            else:
                logger.error(f"Failed to get image (attempt {attempt+1}/{max_retries})")
                keyboard = [
                    [InlineKeyboardButton(f"Невдача!\nПочекайте! ({attempt+1}/{max_retries})", callback_data='wait')]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_reply_markup(reply_markup=reply_markup)
                time.sleep(1)
        else:
            try:
                keyboard = [
                    [InlineKeyboardButton("Підтвердити", callback_data='confirm')],
                    [InlineKeyboardButton(f"Помилка\n(спробувати ще раз)", callback_data='reject')]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_reply_markup(reply_markup=reply_markup)
            except Exception as e:
                logger.error(f"Failed to edit message text: {e}")

# Команда /add_tag
async def add_tag(update: Update, context: CallbackContext) -> None:
    if not is_user_allowed(update):
        return
    tag = ' '.join(context.args)
    if tag:
        if tag not in tags:
            tags.append(tag)
            update_tags_file()
            response = await update.message.reply_text(f'Tег "{tag}" успішно додано.')
        else:
            response = await update.message.reply_text(f'Tег "{tag}" вже існує.')
    else:
        response = await update.message.reply_text('Будь ласка, вкажіть тег для додавання.')

    # Видалити повідомлення користувача та відповідь через 2 секунди
    await delete_message_later(context, update.message.message_id, update.message.chat_id)
    await delete_message_later(context, response.message_id, response.chat_id)

# Команда /remove_tag
async def remove_tag(update: Update, context: CallbackContext) -> None:
    if not is_user_allowed(update):
        return
    tag = ' '.join(context.args)
    if tag:
        if tag in tags:
            tags.remove(tag)
            update_tags_file()
            response = await update.message.reply_text(f'Tег "{tag}" успішно видалено.')
        else:
            response = await update.message.reply_text(f'Tег "{tag}" не знайдено.')
    else:
        response = await update.message.reply_text('Будь ласка, вкажіть тег для видалення.')

    # Видалити повідомлення користувача та відповідь через 2 секунди
    await delete_message_later(context, update.message.message_id, update.message.chat_id)
    await delete_message_later(context, response.message_id, response.chat_id)

# Команда /list_tags
async def list_tags(update: Update, context: CallbackContext) -> None:
    if not is_user_allowed(update):
        return
    if tags:
        await update.message.reply_text('Список тегів:\n' + '\n'.join(tags))
    else:
        await update.message.reply_text('Список тегів порожній.')

# Команда /block_tag
async def block_tag(update: Update, context: CallbackContext) -> None:
    if not is_user_allowed(update):
        return
    tag = ' '.join(context.args)
    if tag:
        if tag not in banned_tags:
            banned_tags.append(tag)
            update_banned_tags_file()
            response = await update.message.reply_text(f'Tег "{tag}" успішно заблоковано.')
        else:
            response = await update.message.reply_text(f'Tег "{tag}" вже заблоковано.')
    else:
        response = await update.message.reply_text('Будь ласка, вкажіть тег для блокування.')

    # Видалити повідомлення користувача та відповідь через 2 секунди
    await delete_message_later(context, update.message.message_id, update.message.chat_id)
    await delete_message_later(context, response.message_id, response.chat_id)

# Команда /unblock_tag
async def unblock_tag(update: Update, context: CallbackContext) -> None:
    if not is_user_allowed(update):
        return
    tag = ' '.join(context.args)
    if tag:
        if tag in banned_tags:
            banned_tags.remove(tag)
            update_banned_tags_file()
            response = await update.message.reply_text(f'Tег "{tag}" успішно розблоковано.')
        else:
            response = await update.message.reply_text(f'Tег "{tag}" не знайдено серед заблокованих.')
    else:
        response = await update.message.reply_text('Будь ласка, вкажіть тег для розблокування.')

    # Видалити повідомлення користувача та відповідь через 2 секунди
    await delete_message_later(context, update.message.message_id, update.message.chat_id)
    await delete_message_later(context, response.message_id, response.chat_id)


# Основна функція
def main() -> None:
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("get_image", get_image))
    application.add_handler(CommandHandler("add_tag", add_tag))
    application.add_handler(CommandHandler("remove_tag", remove_tag))
    application.add_handler(CommandHandler("block_tag", block_tag))
    application.add_handler(CommandHandler("unblock_tag", unblock_tag))
    application.add_handler(CommandHandler("list_tags", list_tags))
    application.add_handler(CallbackQueryHandler(button))

    # Реєстрація обробника помилок
    application.add_error_handler(error_handler)

    # Запуск планувальника
    start_scheduler(application)

    application.run_polling()

# Обробник помилок
async def error_handler(update: Update, context: CallbackContext) -> None:
    logger.error(msg="Exception while handling an update:", exc_info=context.error)

if __name__ == '__main__':
    main()