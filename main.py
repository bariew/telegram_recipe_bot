import logging
import os
import re
import sys
import mysql.connector

from telegram import (Update, InlineKeyboardButton, InlineKeyboardMarkup)
from telegram.ext import (CallbackContext, Updater, Dispatcher, CommandHandler,
                          MessageHandler, CallbackQueryHandler, Filters)

sys.path.insert(0, os.path.abspath(".."))
from local import local_params


logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename=os.path.abspath("./log"),
    filemode='w',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

db = mysql.connector.connect(
    host="localhost",
    user=local_params['database_username'],
    password=local_params['database_password'],
    database="food"
)
cursor = db.cursor(buffered=True, dictionary=True)


def start(update, context):
    update.message.reply_text('Now you can search recipes. '
                              'Type in some ingredients you wish to use (e.g.: potato, egg, pepper):')


def search(update, context):
    where = []
    if update.callback_query:
        chat_id = update.callback_query.message.chat_id
        data = get_callback_data(update)
        page, query = int(data[1]), data[2]
    else:
        chat_id = update.message.chat_id
        page = 0
        query = update.message.text

    params = build_search_query(where, query)
    cursor.execute("SELECT id, `name` FROM recipe WHERE " + ' AND '.join(where)
                   + " LIMIT 10 OFFSET " + str(page*10), params)
    data = cursor.fetchall()
    if len(data) == 0:
        context.bot.send_message(chat_id, "No recipes were found.")
        return

    keyboard = []
    for i in data:
        keyboard.append([InlineKeyboardButton(i["name"], callback_data='id_' + str(i["id"]) + '__query__' + query)])
    if len(keyboard) == 10:
        keyboard.append([InlineKeyboardButton(
            "Page "+str(page+2)+" >>>", callback_data='page_' + str(page+1) + '__query__' + query
        )])

    context.bot.send_message(
        chat_id,
        text='"'+query+'", page ' + str(page+1) + ": ",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


def get_callback_data(update: Update):
    return re.match(r'^[\w]+_(\d+)__query__(.*)$', update.callback_query.data)


def show(update: Update, context, item=None):
    callback_data = get_callback_data(update)
    id, ingredients = callback_data[1], callback_data[2]
    cursor.execute("SELECT * FROM recipe WHERE id="+id)
    item = cursor.fetchone()
    context.bot.send_message(
        update.callback_query.message.chat_id, text(item),
        parse_mode="HTML",
        disable_web_page_preview=False,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(
            "Next >>",
            callback_data='next_' + str(item['id']) + '__query__' + ingredients
        )]])
    )


def build_search_query(where: list, ingredients: str):
    params = re.sub(r'\s*,\s*', ',', ingredients).split(',')
    for i, element in enumerate(params):
        where.append('ingredients LIKE %s')
        params[i] = "%" + element + "%"
    return params


def show_next(update: Update, context: Updater):
    callback_data = get_callback_data(update)
    id, ingredients = callback_data[1], callback_data[2]
    where = ["id > " + str(id)]
    params = build_search_query(where, ingredients)
    cursor.execute("SELECT * FROM recipe WHERE " + ' AND '.join(where) + " LIMIT 1", params)
    item = cursor.fetchone()
    if not item:
        context.bot.send_message(update.callback_query.message.chat_id, "No more recipes found")
        return
    context.bot.send_message(
        update.callback_query.message.chat_id, text(item),
        parse_mode="HTML",
        disable_web_page_preview=False,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(
            "Next >>",
            callback_data='next_' + str(item['id']) + '__query__' + ingredients
        )]])
    )


def text(recipe):
    template = '<b>{name}</b>\n' \
               '<a href="{image}">&#8205;</a>\n' \
               '<i>Preparation: {prepTime}</i>\n' \
               '<i>Cooking : {cookTime}</i>\n\n' \
               '<code>INGREDIENTS: {ingredients}</code>\n' \
               '{description}'
    for i in recipe:
        v = time_format(recipe[i]) if i in ['prepTime', 'cookTime'] \
            else recipe[i] or ''
        template = template.replace('{'+i+'}', str(v))
    return template


def time_format(time: str):
    return time.replace('PT', '').replace('M', ' minute(s)').replace('H', ' hour(s) ') \
        if time is not None else ''


def error_handler(update: Update, context: CallbackContext):
    error: Exception = context.error
    logger.info(error)


def main():
    updater = Updater(local_params['telegram_key'], use_context=True)
    dispatcher: Dispatcher = updater.dispatcher
    dispatcher.add_error_handler(error_handler)
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(MessageHandler(Filters.text, search))
    dispatcher.add_handler(CallbackQueryHandler(show, pattern='id_'))
    dispatcher.add_handler(CallbackQueryHandler(show_next, pattern='next_'))
    dispatcher.add_handler(CallbackQueryHandler(search, pattern='page_'))
    # Start the Bot
    updater.start_polling()
    updater.idle()


if __name__ == '__main__':
    main()
