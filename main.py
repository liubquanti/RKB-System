import logging
import re
import os
import random
import time
import asyncio
import schedule
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, CallbackContext, MessageHandler, filters
import requests
from datetime import datetime, timedelta
from config import TOKEN, CHANNEL_ID, GROUP_ID, ALLOWED_USER_ID
from tags import tags
from rating import rating_tags
from banned import banned_tags

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

def is_image_accessible(url):
    try:
        response = requests.head(url)
        return response.status_code == 200
    except requests.RequestException:
        return False

def get_random_image():
    random_tag = random.choice(tags)
    url = f"https://danbooru.donmai.us/posts.json?tags={random_tag}&random=true"
    
    for _ in range(10):
        response = requests.get(url)
        data = response.json()
        
        if isinstance(data, list) and data:
            random.shuffle(data)
            
            for image_data in data:
                image_url = image_data.get('file_url')
                tag_string = image_data.get('tag_string', '')
                rating = image_data.get('rating', '')

                if any(banned_tag in tag_string for banned_tag in banned_tags):
                    continue

                if any(rating_tag in rating for rating_tag in rating_tags):
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

def clean_character_name(name):
    return re.sub(r'_?\([^)]*\)', '', name)

def update_tags_file():
    with open("tags.py", "w") as file:
        file.write("tags = [\n")
        for tag in tags:
            file.write(f'    "{tag}",\n')
        file.write("]\n")

def update_banned_tags_file():
    with open('banned.py', 'w') as file:
        file.write('banned_tags = [\n')
        for tag in banned_tags:
            file.write(f'    "{tag}",\n')
        file.write(']\n')

async def delete_message_later(context: CallbackContext, message_id: int, chat_id: int, delay: int = 1):
    await asyncio.sleep(delay)
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception as e:
        logger.error(f"Error deleting message: {e}")

def is_user_allowed(update: Update) -> bool:
    return update.effective_user.id == ALLOWED_USER_ID

async def start(update: Update, context: CallbackContext) -> None:
    if not is_user_allowed(update):
        return
    await update.message.reply_text('Вітаю в системі RKB!\n'
                                    '\n'
                                    'Знайти арт: /get_image.\n'
                                    '\n'
                                    'Додати тег: /add_tag <tag>.\n'
                                    'Видалити тег: /remove_tag <tag>.\n'
                                    'Заблокувати тег: /block_tag <tag>.\n'
                                    'Розблокувати тег: /unblock_tag <tag>.\n'
                                    'Всі теги: /list_tags.')
    
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

    schedule_next_job(application)

def schedule_next_job(application: Application) -> None:
    scheduler = application.job_queue.scheduler
    random_minute = random.randint(0, 59)
    now = datetime.now()
    next_run_time = (now + timedelta(hours=1)).replace(minute=random_minute, second=0, microsecond=0)
    logger.info(f"Next image will be published at {next_run_time.strftime('%Y-%m-%d %H:%M:%S')}")
    scheduler.add_job(publish_image, 'date', run_date=next_run_time, args=(application,))

def start_scheduler(application: Application) -> None:
    scheduler = AsyncIOScheduler()
    application.job_queue.scheduler = scheduler
    scheduler.start()
    schedule_next_job(application)

async def get_image(update: Update, context: CallbackContext) -> None:
    if not is_user_allowed(update):
        return
    image_url, published_at, characters, copyright_info, rating, tag_string_general, post_id, artist = get_random_image()
    if image_url:
        if "g" in rating_tags:
            general_state = "🔘"
        else:
            general_state = "🟢"
        if "q" in rating_tags:
            questionable_state = "🔘"
        else:
            questionable_state = "🟠"
        if "s" in rating_tags:
            sensitive_state = "🔘"
        else:
            sensitive_state = "🟡"
        if "e" in rating_tags:
            explicit_state = "🔘"
        else:
            explicit_state = "🔴"
        keyboard = [
            [InlineKeyboardButton("Підтвердити", callback_data='confirm')],
            [InlineKeyboardButton("Відхилити", callback_data='reject')],
            [InlineKeyboardButton(general_state, callback_data='modify_general'), InlineKeyboardButton(sensitive_state, callback_data='modify_sensetive'), InlineKeyboardButton(questionable_state, callback_data='modify_questionable'), InlineKeyboardButton(explicit_state, callback_data='modify_explicit')],
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
                    if "g" in rating_tags:
                        general_state = "🔘"
                    else:
                        general_state = "🟢"
                    if "q" in rating_tags:
                        questionable_state = "🔘"
                    else:
                        questionable_state = "🟠"
                    if "s" in rating_tags:
                        sensitive_state = "🔘"
                    else:
                        sensitive_state = "🟡"
                    if "e" in rating_tags:
                        explicit_state = "🔘"
                    else:
                        explicit_state = "🔴"
                    keyboard = [
                        [InlineKeyboardButton("Підтвердити", callback_data='confirm')],
                        [InlineKeyboardButton("Відхилити", callback_data='reject')],
                        [InlineKeyboardButton(general_state, callback_data='modify_general'), InlineKeyboardButton(sensitive_state, callback_data='modify_sensetive'), InlineKeyboardButton(questionable_state, callback_data='modify_questionable'), InlineKeyboardButton(explicit_state, callback_data='modify_explicit')],
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
                if "g" in rating_tags:
                    general_state = "🔘"
                else:
                    general_state = "🟢"
                if "q" in rating_tags:
                    questionable_state = "🔘"
                else:
                    questionable_state = "🟠"
                if "s" in rating_tags:
                    sensitive_state = "🔘"
                else:
                    sensitive_state = "🟡"
                if "e" in rating_tags:
                    explicit_state = "🔘"
                else:
                    explicit_state = "🔴"
                keyboard = [
                    [InlineKeyboardButton("Підтвердити", callback_data='confirm')],
                    [InlineKeyboardButton("Відхилити", callback_data='reject')],
                    [InlineKeyboardButton(general_state, callback_data='modify_general'), InlineKeyboardButton(sensitive_state, callback_data='modify_sensetive'), InlineKeyboardButton(questionable_state, callback_data='modify_questionable'), InlineKeyboardButton(explicit_state, callback_data='modify_explicit')],
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
                states = {
                    "g": "🟢",
                    "q": "🟠",
                    "s": "🟡",
                    "e": "🔴"
                }
                rating_states = {tag: "🔘" if tag in rating_tags else states[tag] for tag in states}
                keyboard = [
                    [InlineKeyboardButton("Підтвердити", callback_data='confirm')],
                    [InlineKeyboardButton(f"Помилка\n(спробувати ще раз)", callback_data='reject')],
                    [InlineKeyboardButton(rating_states["g"], callback_data='modify_general'), 
                     InlineKeyboardButton(rating_states["s"], callback_data='modify_sensetive'), 
                     InlineKeyboardButton(rating_states["q"], callback_data='modify_questionable'), 
                     InlineKeyboardButton(rating_states["e"], callback_data='modify_explicit')]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_reply_markup(reply_markup=reply_markup)
            except Exception as e:
                logger.error(f"Failed to edit message text: {e}")

    elif query.data.startswith('modify_'):
        tag_to_modify = query.data.split('_')[1][0]
        if tag_to_modify in rating_tags:
            rating_tags.remove(tag_to_modify)
        else:
            rating_tags.append(tag_to_modify)

        states = {
            "g": "🟢",
            "q": "🟠",
            "s": "🟡",
            "e": "🔴"
        }
        rating_states = {tag: "🔘" if tag in rating_tags else states[tag] for tag in states}
        keyboard = [
            [InlineKeyboardButton("Підтвердити", callback_data='confirm')],
            [InlineKeyboardButton(f"Відхилити", callback_data='reject')],
            [InlineKeyboardButton(rating_states["g"], callback_data='modify_general'), 
             InlineKeyboardButton(rating_states["s"], callback_data='modify_sensetive'), 
             InlineKeyboardButton(rating_states["q"], callback_data='modify_questionable'), 
             InlineKeyboardButton(rating_states["e"], callback_data='modify_explicit')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_reply_markup(reply_markup=reply_markup)

        with open("rating.py", "w") as file:
            file.write("rating_tags = [\n")
            for g in rating_tags:
                file.write(f'    "{g}",\n')
            file.write("]\n")
    


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

    await delete_message_later(context, update.message.message_id, update.message.chat_id)
    await delete_message_later(context, response.message_id, response.chat_id)

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

    await delete_message_later(context, update.message.message_id, update.message.chat_id)
    await delete_message_later(context, response.message_id, response.chat_id)

async def list_tags(update: Update, context: CallbackContext) -> None:
    if not is_user_allowed(update):
        return
    if tags:
        await update.message.reply_text('Список тегів:\n' + '\n'.join(tags))
    else:
        await update.message.reply_text('Список тегів порожній.')

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

    await delete_message_later(context, update.message.message_id, update.message.chat_id)
    await delete_message_later(context, response.message_id, response.chat_id)

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

    await delete_message_later(context, update.message.message_id, update.message.chat_id)
    await delete_message_later(context, response.message_id, response.chat_id)



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
    application.add_error_handler(error_handler)
    start_scheduler(application)
    application.run_polling()

async def error_handler(update: Update, context: CallbackContext) -> None:
    logger.error(msg="Exception while handling an update:", exc_info=context.error)

if __name__ == '__main__':
    main()