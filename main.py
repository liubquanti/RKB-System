import re
import os
import random
import time
import asyncio
import schedule
from colorama import Fore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, CallbackContext, MessageHandler, filters
import requests
from datetime import datetime, timedelta
from config import TOKEN, CHANNEL_ID, ALLOWED_USER_ID, MODE
from tags import tags
from rating import rating_tags
from banned import banned_tags

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
        try:
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()
        except (requests.RequestException, ValueError) as e:
            print(f"{Fore.RED}[WRN] Не вдалося отримати дані фото: {e}{Fore.RESET}")
            continue

        if not isinstance(data, list) or not data:
            continue

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
                return (
                    image_url,
                    image_data.get('created_at'),
                    image_data.get('tag_string_character', '').replace(' ', ', '),
                    image_data.get('tag_string_copyright', ''),
                    rating,
                    image_data.get('tag_string_general', ''),
                    image_data.get('id'),
                    image_data.get('tag_string_artist', '')
                )

    return None, None, None, None, None, None, None, None

def clean_character_name(name):
    return (name)

def clean_character_name_publish(name):
    cleaned_name = re.sub(r'\([^)]*\)', '', name)
    cleaned_name = '_'.join(word.capitalize() if word.islower() else word for word in cleaned_name.split('_'))
    cleaned_name = re.sub(r'[^a-zA-Z0-9_]', '', cleaned_name)
    return cleaned_name.rstrip('_')

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
        print(f"{Fore.RED}[WRN] Не вдалося видалити повідомлення: {e}{Fore.RESET}")

def is_user_allowed(update: Update) -> bool:
    return update.effective_user.id == ALLOWED_USER_ID

async def start(update: Update, context: CallbackContext) -> None:
    if not is_user_allowed(update):
        args = context.args
        if args:
            post_id = args[0]
            url = f"https://danbooru.donmai.us/posts/{post_id}.json"
            try:
                response = requests.get(url)
                response.raise_for_status()
                data = response.json()
                image_url = data.get('file_url')
                if image_url and is_image_accessible(image_url):
                    await update.message.reply_text('🤗  •  Надсилаємо вам арт!')
                    await update.message.reply_document(document=image_url)
                    user_name = update.effective_user.full_name
                    await context.bot.send_message(chat_id=ALLOWED_USER_ID, text=f"👀  •  Користувач {user_name} (<a href='tg://user?id={update.effective_user.id}'>{update.effective_user.id}</a>) отримав <a href='https://t.me/rkbsystem_bot?start={post_id}'>фото</a>.", parse_mode='HTML')
                    return
            except (requests.RequestException, ValueError) as e:
                print(f"{Fore.RED}[WRN] Не вдалося отримати дані фото: {e}{Fore.RESET}")
        await update.message.reply_text('🍓  •  Вітаю в системі RKB!\n\n😨  •  Схоже, що Ви прийшли не з нашого каналу. Цей бот призначений, щоб швидко отримувати арти без стиснення, які публікуються в потоці @rkbsystem.\n\n👀  •  Якщо Ви прийшли за артами, то радимо підписатися на канал @rkbsystem. І пізніше зможете тут отримати роботи, які Вам сподобаються.')
    if not is_user_allowed(update):
        return
    args = context.args
    if args:
        post_id = args[0]
        url = f"https://danbooru.donmai.us/posts/{post_id}.json"
        try:
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()
            image_url = data.get('file_url')
            if image_url and is_image_accessible(image_url):
                await update.message.reply_document(document=image_url)
                return
        except (requests.RequestException, ValueError) as e:
            print(f"{Fore.RED}[WRN] Не вдалося отримати дані фото: {e}{Fore.RESET}")
    await update.message.reply_text('🍓  •  Вітаю в системі RKB!\n'
                                    '\n'
                                    '🔎  •  Знайти арт: /get_image.\n'
                                    '\n'
                                    '➕  •  Додати тег: /add_tag <tag>.\n'
                                    '➖  •  Видалити тег: /remove_tag <tag>.\n'
                                    '🚫  •  Заблокувати тег: /block_tag <tag>.\n'
                                    '✅  •  Розблокувати тег: /unblock_tag <tag>.\n'
                                    '📃  •  Всі теги: /list_tags.')
    
async def publish_image(application: Application) -> None:
    image_data = get_random_image()
    if not image_data[0]:
        print(f"{Fore.RED}[WRN] Не вдалося отримати фото.{Fore.RESET}")
        return

    image_url, published_at, characters, copyright_info, rating, tag_string_general, post_id, artist = image_data

    cleaned_characters = {clean_character_name(char) for char in characters.split(', ')}
    character_hashtags = ' '.join(f"#{char}" for char in cleaned_characters)

    cleaned_copyrights = {clean_character_name(copyright) for copyright in copyright_info.split(' ')}
    copyright_hashtags = ' '.join(f"#{copyright}" for copyright in cleaned_copyrights)

    cleaned_characters_publish = {clean_character_name_publish(char) for char in characters.split(', ')}
    character_hashtags_publish = ' '.join(f"#{char}" for char in cleaned_characters_publish)

    cleaned_copyrights_publish = {clean_character_name_publish(copyright) for copyright in copyright_info.split(' ')}
    copyright_hashtags_publish = ' '.join(f"#{copyright}" for copyright in cleaned_copyrights_publish)

    rating_map = {
        'g': '🟢  •  #general',
        's': '🟡  •  #sensetive',
        'q': '🟠  •  #questionable',
        'e': '🔴  •  #explicit'
    }
    rating = rating_map.get(rating, rating)

    hashtags = f"{character_hashtags}\n🌐  •  {copyright_hashtags}"
    channel_hashtags = '\n'.join(f"🎭  •  #{char}" for char in cleaned_characters_publish) + '\n' + \
                       '\n'.join(f"🌐  •  #{copyright}" for copyright in cleaned_copyrights_publish) + \
                       f"\n\n✒️  •  <a href='https://t.me/rkbsystem_bot?start={post_id}'>Арт без стиснення</a>\n\n🍓  •  <a href='https://t.me/rkbsystem'>Підписатися на RKBS</a>"
    post_url = f"https://danbooru.donmai.us/posts/{post_id}"
    re.sub(r'_?\([^)]*\)', '', artist)

    caption = (
        f"🕒  •  {datetime.fromisoformat(published_at).strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"🪶  •  #{artist}\n"
        f"🎭  •  {hashtags if hashtags else 'Немає тегів'}\n"
        f"{rating}\n"
        f"🔗  •  <a href='{post_url}'>Посилання</a>"
    )
    channel_caption = channel_hashtags if channel_hashtags else 'Немає тегів'

    try:
        await application.bot.send_photo(chat_id=CHANNEL_ID, photo=image_url, caption=channel_caption, parse_mode='HTML')
        print(f"{Fore.YELLOW}[LOG] Фото успішно опублікувано.{Fore.RESET}")
    except Exception as e:
        print(f"{Fore.RED}[WRN] Не вдалося відправити фото: {e}{Fore.RESET}")


    schedule_next_job(application)

def schedule_next_job(application: Application) -> None:
    scheduler = application.job_queue.scheduler
    random_minute = random.randint(0, 59)
    now = datetime.now()
    next_run_time = (now + timedelta(hours=1)).replace(minute=random_minute, second=0, microsecond=0)
    print(f"{Fore.YELLOW}[LOG] Наступне фото буде відправлено: {next_run_time.strftime('%Y-%m-%d %H:%M:%S')}{Fore.RESET}")
    scheduler.add_job(publish_image, 'date', run_date=next_run_time, args=(application,))

def start_scheduler(application: Application) -> None:
    scheduler = AsyncIOScheduler()
    application.job_queue.scheduler = scheduler
    scheduler.start()
    schedule_next_job(application)

async def get_image(update: Update, context: CallbackContext) -> None:
    if not is_user_allowed(update):
        return

    image_data = get_random_image()
    if not image_data[0]:
        await update.message.reply_text('Не вдалося отримати зображення. Спробуйте ще раз.')
        return

    image_url, published_at, characters, copyright_info, rating, tag_string_general, post_id, artist = image_data

    rating_states = {
        "g": "🔘" if "g" in rating_tags else "🟢",
        "q": "🔘" if "q" in rating_tags else "🟠",
        "s": "🔘" if "s" in rating_tags else "🟡",
        "e": "🔘" if "e" in rating_tags else "🔴"
    }

    keyboard = [
        [InlineKeyboardButton("✅ Підтвердити", callback_data='confirm'),
         InlineKeyboardButton("❌ Відхилити", callback_data='reject')],
        [InlineKeyboardButton("🎭", callback_data='block_character'),
         InlineKeyboardButton("🪶", callback_data='block_author')],
        [InlineKeyboardButton(rating_states["g"], callback_data='modify_general'),
         InlineKeyboardButton(rating_states["s"], callback_data='modify_sensetive'),
         InlineKeyboardButton(rating_states["q"], callback_data='modify_questionable'),
         InlineKeyboardButton(rating_states["e"], callback_data='modify_explicit')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    cleaned_characters = {clean_character_name(char) for char in characters.split(', ')}
    character_hashtags = ' '.join(f"#{char}" for char in cleaned_characters)

    cleaned_copyrights = {clean_character_name(copyright) for copyright in copyright_info.split(' ')}
    copyright_hashtags = ' '.join(f"#{copyright}" for copyright in cleaned_copyrights)

    cleaned_characters_publish = {clean_character_name_publish(char) for char in characters.split(', ')}
    character_hashtags_publish = ' '.join(f"#{char}" for char in cleaned_characters_publish)

    cleaned_copyrights_publish = {clean_character_name_publish(copyright) for copyright in copyright_info.split(' ')}
    copyright_hashtags_publish = ' '.join(f"#{copyright}" for copyright in cleaned_copyrights_publish)

    tag_string_general = tag_string_general.replace(' ', '\n')

    rating_map = {
        'g': '🟢  •  #general',
        's': '🟡  •  #sensetive',
        'q': '🟠  •  #questionable',
        'e': '🔴  •  #explicit'
    }
    rating = rating_map.get(rating, rating)

    hashtags = f"{character_hashtags}\n🌐  •  {copyright_hashtags}"
    channel_hashtags = '\n'.join(f"🎭  •  #{char}" for char in cleaned_characters_publish) + '\n' + \
                       '\n'.join(f"🌐  •  #{copyright}" for copyright in cleaned_copyrights_publish) + \
                       f"\n\n✒️  •  <a href='https://t.me/rkbsystem_bot?start={post_id}'>Арт без стиснення</a>\n\n🍓  •  <a href='https://t.me/rkbsystem'>Підписатися на RKBS</a>"
    post_url = f"https://danbooru.donmai.us/posts/{post_id}"

    caption = (
        f"🕒  •  {datetime.fromisoformat(published_at).strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"🪶  •  #{artist}\n"
        f"🎭  •  {hashtags if hashtags else 'Немає тегів'}\n"
        f"{rating}\n"
        f"🔗  •  <a href='{post_url}'>Посилання</a>\n"
        f"<blockquote expandable>{tag_string_general}\n</blockquote>"
    )
    channel_caption = channel_hashtags if channel_hashtags else 'Немає тегів'

    context.user_data['current_image'] = image_url
    context.user_data['current_caption'] = caption
    context.user_data['current_channel_caption'] = channel_caption

    await update.message.reply_photo(photo=image_url, caption=caption, reply_markup=reply_markup, parse_mode='HTML', show_caption_above_media=True)

async def button(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()

    def get_rating_states():
        states = {
            "g": "🟢",
            "q": "🟠",
            "s": "🟡",
            "e": "🔴"
        }
        return {tag: "🔘" if tag in rating_tags else states[tag] for tag in states}

    def create_keyboard():
        rating_states = get_rating_states()
        return [
            [InlineKeyboardButton("✅ Підтвердити", callback_data='confirm'),
             InlineKeyboardButton("❌ Відхилити", callback_data='reject')],
            [InlineKeyboardButton("🎭", callback_data='block_character'),
             InlineKeyboardButton("🪶", callback_data='block_author')],
            [InlineKeyboardButton(rating_states["g"], callback_data='modify_general'), 
             InlineKeyboardButton(rating_states["s"], callback_data='modify_sensetive'), 
             InlineKeyboardButton(rating_states["q"], callback_data='modify_questionable'), 
             InlineKeyboardButton(rating_states["e"], callback_data='modify_explicit')]
        ]

    async def edit_message_with_retry(attempt, max_retries, image_url, caption, reply_markup, parse_mode, show_caption_above_media):
        try:
            await query.edit_message_media(media=InputMediaPhoto(image_url, caption=caption, parse_mode=parse_mode, show_caption_above_media=show_caption_above_media), reply_markup=reply_markup)
            return True
        except Exception as e:
            print(f"{Fore.RED}[WRN] Не вдалося отримати фото: (спроба {attempt+1}/{max_retries}) {e}{Fore.RESET}")
            await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton(f"Невдача!\nПочекайте! ({attempt+1}/{max_retries})", callback_data='wait')]]
            ))
            time.sleep(1)
            return False

    if query.data == 'confirm':
        image_url = context.user_data.get('current_image')
        channel_caption = context.user_data.get('current_channel_caption')
        if image_url:
            try:
                await context.bot.send_photo(chat_id=CHANNEL_ID, photo=image_url, caption=channel_caption, parse_mode='HTML')
                await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton(f"Опублікувано!", callback_data='reject')]]
                ))
                print(f"{Fore.YELLOW}[LOG] Фото опубліковано!{Fore.RESET}")
                time.sleep(1)
                await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(create_keyboard()))
            except Exception as e:
                print(f"{Fore.RED}[WRN] Не вдалося відправити фото: {e}{Fore.RESET}")
                await query.edit_message_text(text="Не вдалося опублікувати зображення.")
    elif query.data == 'reject':
        max_retries = 5
        for attempt in range(max_retries):
            image_url, published_at, characters, copyright_info, rating, tag_string_general, post_id, artist = get_random_image()
            if image_url:
                cleaned_characters = {clean_character_name(char) for char in characters.split(', ')}
                character_hashtags = ' '.join(f"#{char}" for char in cleaned_characters)
                cleaned_copyrights = {clean_character_name(copyright) for copyright in copyright_info.split(' ')}
                copyright_hashtags = ' '.join(f"#{copyright}" for copyright in cleaned_copyrights)

                cleaned_characters_publish = {clean_character_name_publish(char) for char in characters.split(', ')}
                character_hashtags_publish = ' '.join(f"#{char}" for char in cleaned_characters_publish)

                cleaned_copyrights_publish = {clean_character_name_publish(copyright) for copyright in copyright_info.split(' ')}
                copyright_hashtags_publish = ' '.join(f"#{copyright}" for copyright in cleaned_copyrights_publish)

                tag_string_general = tag_string_general.replace(' ', '\n')

                rating = {
                    'g': '🟢  •  #general',
                    's': '🟡  •  #sensetive',
                    'q': '🟠  •  #questionable',
                    'e': '🔴  •  #explicit'
                }.get(rating, rating)
                hashtags = character_hashtags + '\n🌐  •  ' + copyright_hashtags
                channel_hashtags = '\n'.join(f"🎭  •  #{char}" for char in cleaned_characters_publish) + '\n' + \
                                   '\n'.join(f"🌐  •  #{copyright}" for copyright in cleaned_copyrights_publish) + \
                                   f"\n\n✒️  •  <a href='https://t.me/rkbsystem_bot?start={post_id}'>Арт без стиснення</a>\n\n🍓  •  <a href='https://t.me/rkbsystem'>Підписатися на RKBS</a>"
                post_url = f"https://danbooru.donmai.us/posts/{post_id}"
                caption = (
                    f"🕒  •  {datetime.fromisoformat(published_at).strftime('%Y-%m-%d %H:%M:%S')}\n"
                    f"🪶  •  #{artist}\n"
                    f"🎭  •  {hashtags if hashtags else 'Немає тегів'}\n"
                    f"{rating}\n"
                    f"🔗  •  <a href='{post_url}'>Посилання</a>\n"
                    f"<blockquote expandable>{tag_string_general}\n</blockquote>"
                )
                channel_caption = f"{channel_hashtags if channel_hashtags else 'Немає тегів'}"
                context.user_data['current_image'] = image_url
                context.user_data['current_caption'] = caption
                context.user_data['current_channel_caption'] = channel_caption
                if await edit_message_with_retry(attempt, max_retries, image_url, caption, InlineKeyboardMarkup(create_keyboard()), parse_mode='HTML', show_caption_above_media=True):
                    break
        else:
            await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(create_keyboard()))
    elif query.data == 'block_character':
        characters = context.user_data.get('current_caption').split('\n')[2].replace('🎭  •  ', '').split(' ')
        characters = [char.replace('#', '') for char in characters if char]

        if characters:
            character_buttons = [[InlineKeyboardButton(char, callback_data=f'ban_{char}')] for char in characters]
            character_buttons.append([InlineKeyboardButton("Відмінити", callback_data='cancel')])
            await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(character_buttons))
        else:
            await query.message.reply_text('Немає персонажів для блокування.')
    elif query.data.startswith('ban_'):
        char_to_ban = query.data.split('_', 1)[1]
        if char_to_ban and char_to_ban not in banned_tags:
            banned_tags.append(char_to_ban)
            update_banned_tags_file()
            response = await query.message.reply_text(f'Персонаж "{char_to_ban}" успішно заблоковано.')
            await delete_message_later(context, response.message_id, response.chat_id, delay=1)
        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(create_keyboard()))
    elif query.data == 'cancel':
        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(create_keyboard()))
    elif query.data.startswith('modify_'):
        tag_to_modify = query.data.split('_')[1][0]
        if tag_to_modify in rating_tags:
            rating_tags.remove(tag_to_modify)
        else:
            rating_tags.append(tag_to_modify)
        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(create_keyboard()))
        with open("rating.py", "w") as file:
            file.write("rating_tags = [\n")
            for g in rating_tags:
                file.write(f'    "{g}",\n')
            file.write("]\n")
    elif query.data == 'block_author':
        author = context.user_data.get('current_caption').split('\n')[1].replace('Арт: #', '')
        if author:
            banned_tags.append(author)
            update_banned_tags_file()
            response = await query.message.reply_text(f'Автор "{author}" успішно заблоковано.')
            await delete_message_later(context, response.message_id, response.chat_id, delay=1)
        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(create_keyboard()))

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
    if MODE == 'self':
        start_scheduler(application)
    application.run_polling()

async def error_handler(update: Update, context: CallbackContext) -> None:
    print(f"{Fore.RED}[WRN] Виняток під час обробки оновлення: {context.error}{Fore.RESET}")

if __name__ == '__main__':
    print(f"{Fore.YELLOW}[LOG] Систему RKB запущено!{Fore.RESET}")
    main()