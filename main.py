import logging
import os
import re
import sys
import html

from mysql import connector
import time

from telegram import (Update, InlineKeyboardButton, InlineKeyboardMarkup)
from telegram.ext import (CallbackContext, Updater, Dispatcher, Handler, CommandHandler,
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


class DbRecord:
    db = connector.connect(
        host="localhost",
        user=local_params['database_username'],
        password=local_params['database_password'],
        database="food"
    )

    def db_execute(self, callback: callable):
        if not self.db.is_connected():
            self.db.reconnect()
        cursor = self.db.cursor(buffered=True, dictionary=True)
        result = callback(self.db, cursor)
        cursor.close()
        return result[1]

    def fetchone(self, sql, params=()):
        return self.db_execute(lambda db, cursor: [cursor.execute(sql, params), cursor.fetchone()])

    def fetchall(self, sql, params=()):
        return self.db_execute(lambda db, cursor: [cursor.execute(sql, params), cursor.fetchall()])

    def commit(self, sql, params=()):
        return self.db_execute(lambda db, cursor: [cursor.execute(sql, params), db.commit()])


class User(DbRecord):
    ROLE_USER = 0
    ROLE_TESTER = 10
    ROLE_ADMIN = 100

    DATE_FORMAT = '%Y-%m-%d'

    user_id = 0
    role = ROLE_USER
    date = time.strftime(DATE_FORMAT)
    calls = 0

    def __init__(self, data: dict):
        for i in data:
            v = str(data[i]) if i in ['date'] else data[i]
            self.__setattr__(i, v)

    def get(self, user_id):
        data = self.fetchone("SELECT * FROM user WHERE user_id = %s", [user_id])
        if not data:
            return None
        today = time.strftime(User.DATE_FORMAT)
        if str(data['date']) < today:
            data['date'] = today
            data['calls'] = 0
        return User(data)

    def update(self, data: dict):
        update = []
        for i in data:
            self.__setattr__(i, data[i])
            update.append(i + "=%s")
        self.commit(
            "UPDATE user SET " + ", ".join(update) + " WHERE user_id="+str(self.user_id),
            list(data.values())
        )

    def create(self, user_id, role=ROLE_USER):
        data = {'user_id': user_id, 'date': time.strftime(User.DATE_FORMAT), 'role': role, 'calls': 0}
        self.commit(
            "INSERT INTO `user` (`user_id`, `date`, `role`, `calls`) VALUES (%s, %s, %s, %s)",
            list(data.values())
        )
        return User(data)

    def limit_exceed(self):
        return self.role == User.ROLE_USER and self.calls >= 10 and self.date == time.strftime(User.DATE_FORMAT)


class Recipe(DbRecord):

    ERROR_SKIP = 'skip'
    user: User = None

    @staticmethod
    def main():
        model = Recipe()
        updater = Updater(local_params['telegram_key'], use_context=True)
        dispatcher: Dispatcher = updater.dispatcher

        dispatcher.add_error_handler(model.error_handler)
        dispatcher.add_handler(CommandHandler("i_am_special", model.i_am_special), 2)
        # main functionality
        dispatcher.add_handler(CommandHandler("start", model.start), 3)
        dispatcher.add_handler(MessageHandler(Filters.text, model.search), 3)
        dispatcher.add_handler(CallbackQueryHandler(model.show, pattern='id_'), 3)
        dispatcher.add_handler(CallbackQueryHandler(model.show_next, pattern='next_'), 3)
        dispatcher.add_handler(CallbackQueryHandler(model.search, pattern='page_'), 3)

        # Start the Bot
        updater.start_polling()
        updater.idle()

    # HANDLERS

    @staticmethod
    def start(update: Update, context: CallbackContext):
        update.message.reply_text('Now you can search recipes. '
                                  'Type in some ingredients you wish to use (e.g.: potato, egg, pepper):')

    def check(self, update: Update):
        message = update.message or update.callback_query.message
        if not update.effective_user:
            message.reply_text("Not available for unregistered users")
            raise Exception(self.ERROR_SKIP)
        if (not self.user) or (not self.user.user_id == update.effective_user.id):
            self.user = User.get(User({}), update.effective_user.id) or User.create(User({}), update.effective_user.id)
        if update.message and update.message.text in ['/i_am_special', '/start']:
            return None
        if self.user.limit_exceed():
            message.reply_text("10 calls per day limit exceed")
            raise Exception(self.ERROR_SKIP)
        self.user.update({"calls": self.user.calls+1, 'date': self.user.date})
        return None

    def i_am_special(self, update: Update, context: CallbackContext):
        self.user.update({'role': User.ROLE_TESTER})

    def search(self, update: Update, context: CallbackContext):
        self.check(update)
        where = []
        if update.callback_query:
            chat_id = update.callback_query.message.chat_id
            data = Recipe.get_callback_data(update)
            page, query = int(data[1]), data[2]
        else:
            chat_id = update.message.chat_id
            page = 0
            query = update.message.text

        params = Recipe.build_search_query(where, query)
        data = self.fetchall("SELECT id, `name` FROM recipe WHERE " + ' AND '.join(where) +
                             " LIMIT 10 OFFSET " + str(page * 10), params)
        if len(data) == 0:
            context.bot.send_message(chat_id, "No recipes were found.")
            return

        keyboard = []
        for i in data:
            keyboard.append([InlineKeyboardButton(
                html.unescape(i["name"]),
                callback_data='id_' + str(i["id"]) + '__query__' + query
            )])
        if len(keyboard) == 10:
            keyboard.append([InlineKeyboardButton(
                "Page " + str(page + 2) + " >>>", callback_data='page_' + str(page + 1) + '__query__' + query
            )])

        context.bot.send_message(
            chat_id,
            text='"' + query + '", page ' + str(page + 1) + ": ",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    def show(self, update: Update, context: CallbackContext):
        self.check(update)
        callback_data = Recipe.get_callback_data(update)
        id, ingredients = callback_data[1], callback_data[2]
        item = self.fetchone("SELECT * FROM recipe WHERE id=%s", [id])
        context.bot.send_message(
            update.callback_query.message.chat_id, Recipe.text(item),
            parse_mode="HTML",
            disable_web_page_preview=False,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(
                "Next >>",
                callback_data='next_' + str(item['id']) + '__query__' + ingredients
            )]])
        )

    def show_next(self, update: Update, context: CallbackContext):
        self.check(update)
        callback_data = Recipe.get_callback_data(update)
        id, ingredients = callback_data[1], callback_data[2]
        where = ["id > " + str(id)]
        params = Recipe.build_search_query(where, ingredients)
        item = self.fetchone("SELECT * FROM recipe WHERE " + ' AND '.join(where) + " LIMIT 1", params)
        if not item:
            context.bot.send_message(update.callback_query.message.chat_id, "No more recipes found")
            return
        context.bot.send_message(
            update.callback_query.message.chat_id, Recipe.text(item),
            parse_mode="HTML",
            disable_web_page_preview=False,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(
                "Next >>",
                callback_data='next_' + str(item['id']) + '__query__' + ingredients
            )]])
        )

    @staticmethod
    def error_handler(update: Update, context: CallbackContext):
        if context.error.__str__() == Recipe.ERROR_SKIP:
            return
        logger.info(context.error)
        print(context.error)

    # HELPERS

    @staticmethod
    def text(recipe):
        template = '<b>{name}</b>\n' \
                   '<a href="{image}">&#8205;</a>\n' \
                   '<i>Preparation: {prepTime}</i>\n' \
                   '<i>Cooking : {cookTime}</i>\n\n' \
                   '<code>INGREDIENTS: {ingredients}</code>\n' \
                   '{description}'
        for i in recipe:
            v = Recipe.time_format(recipe[i]) if i in ['prepTime', 'cookTime'] \
                else recipe[i] or ''
            template = template.replace('{' + i + '}', str(v))
        return html.unescape(template)

    @staticmethod
    def get_callback_data(update: Update):
        return re.match(r'^[\w]+_(\d+)__query__(.*)$', update.callback_query.data)

    @staticmethod
    def time_format(value: str):
        return value.replace('PT', '').replace('M', ' minute(s)').replace('H', ' hour(s) ') \
            if value is not None else ''

    @staticmethod
    def build_search_query(where: list, ingredients: str):
        params = re.sub(r'\s*,\s*', ',', ingredients).split(',')
        for i, element in enumerate(params):
            where.append('ingredients LIKE %s')
            params[i] = "%" + element + "%"
        return params


if __name__ == '__main__':
    Recipe.main()
