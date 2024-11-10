import random
import psycopg2
from telebot import types, TeleBot, custom_filters
from telebot.storage import StateMemoryStorage
from telebot.handler_backends import State, StatesGroup
from dotenv import load_dotenv
import os

# Загрузка переменных
load_dotenv()
telegram_token = os.getenv('telegram_token')
database = os.getenv('database')
user = os.getenv('user')
password = os.getenv('password')

print('Start telegram bot...')

# Инициализация бота и состояний
bot = TeleBot(telegram_token)
state_storage = StateMemoryStorage()


def show_hint(*lines: str) -> str:
    """
    Объединяет строки в одну с переносами строк.

    :param lines: Строки для объединения.
    :return: Объединенная строка с переносами строк.
    """
    return '\n'.join(lines)


def show_translate(data: dict) -> str:
    """
    Возвращает перевод слова в формате "английское слово -> русское слово".

    :param data: Словарь с данными, содержащий ключи 'eng_word' и 'rus_word'.
    :return: Строка с переводом слова.
    """
    return f'{data["eng_word"]} -> {data["rus_word"]}'


def get_user_id(chat_id: int) -> int:
    """
    Получает user_id в БД пользователя по id чата в телеграм.

    :param chat_id: ID чата в телеграм.
    :return: user_id пользователя в БД.
    """
    conn = psycopg2.connect(database=database, user=user, password=password)
    cur = conn.cursor()
    cur.execute('SELECT user_id FROM users WHERE tg_chat_id = %s', (chat_id,))
    user_id = cur.fetchone()[0]
    cur.close()
    conn.close()
    return user_id


class Command:
    """
    Класс для хранения команд бота.
    """
    ADD_WORD = 'Добавить слово ➕'
    DELETE_WORD = 'Удалить слово 🔙'
    NEXT = 'Дальше ⏭'
    SHOW_WORDS = 'Изучаемые слова 📝'


class MyStates(StatesGroup):
    """
    Класс для хранения состояний бота.
    """
    eng_word = State()
    rus_word = State()
    other_words = State()


@bot.message_handler(commands=['cards', 'start'])
def create_cards(message: types.Message) -> None:
    """
    Обрабатывает команды /cards и /start.
    Создает карточки с английскими словами и командами.

    :param message: Сообщение от пользователя.
    """
    conn = psycopg2.connect(database=database, user=user, password=password)
    cur = conn.cursor()
    chat_id = message.chat.id

    cur.execute('SELECT user_id FROM users WHERE tg_chat_id = %s', (chat_id,))

    if not cur.fetchone():
        bot.send_message(chat_id, """Привет 👋 Давай попрактикуемся в английском языке. Тренировки можешь проходить \
        в удобном для себя темпе.
        
У тебя есть возможность использовать тренажёр, как конструктор, и собирать свою собственную базу для обучения, а также \
можешь смотреть изучаемые в данный момент слова. Для этого воспользуйся инструментами:

Изучаемые слова 📝        
Добавить слово ➕,
Удалить слово 🔙.
Ну что, начнём ⬇️""")

        cur.execute('INSERT INTO users (tg_chat_id) VALUES (%s)', (chat_id,))
        conn.commit()

    cur.execute('SELECT user_id FROM users WHERE tg_chat_id = %s', (message.chat.id,))
    user_id = cur.fetchone()[0]
    cur.execute("""
        SELECT w.rus_word, w.eng_word
        FROM words w
        LEFT JOIN user_words uw ON w.word_id = uw.word_id
        WHERE uw.user_id IS NULL
                OR (uw.user_id = %s AND NOT uw.is_deleted)
                OR (uw.user_id != %s AND uw.is_deleted AND NOT EXISTS (
                    SELECT 1
                    FROM user_words uw2
                    WHERE uw2.word_id = w.word_id
                    AND uw2.user_id = %s
                    AND uw2.is_deleted
                ))
        ORDER BY RANDOM()
        LIMIT 1
    """, (user_id, user_id, user_id))
    rus_word, eng_word = cur.fetchone()

    cur.execute('SELECT user_id FROM users WHERE tg_chat_id = %s', (message.chat.id,))
    user_id = cur.fetchone()[0]
    cur.execute("""
        SELECT w.eng_word
        FROM words w
        LEFT JOIN user_words uw ON w.word_id = uw.word_id
        WHERE w.eng_word != %s
            AND (
                uw.user_id IS NULL
                OR (uw.user_id = %s AND NOT uw.is_deleted)
                OR (uw.user_id != %s AND uw.is_deleted AND NOT EXISTS (
                    SELECT 1
                    FROM user_words uw2
                    WHERE uw2.word_id = w.word_id
                    AND uw2.user_id = %s
                    AND uw2.is_deleted
                ))
            )
        ORDER BY RANDOM()
        LIMIT 3
    """, (eng_word, user_id, user_id, user_id))
    other_words = [row[0] for row in cur.fetchall()]

    cur.close()
    conn.close()

    markup = types.ReplyKeyboardMarkup(row_width=2)

    buttons = [types.KeyboardButton(eng_word)] + [types.KeyboardButton(word) for word in other_words]
    random.shuffle(buttons)
    buttons.extend([
        types.KeyboardButton(Command.SHOW_WORDS),
        types.KeyboardButton(Command.NEXT),
        types.KeyboardButton(Command.ADD_WORD),
        types.KeyboardButton(Command.DELETE_WORD)
    ])
    markup.add(*buttons)

    greeting = f'Выбери перевод слова:\n🇷🇺 {rus_word}'
    bot.send_message(message.chat.id, greeting, reply_markup=markup)
    bot.set_state(message.from_user.id, MyStates.eng_word, message.chat.id)
    with bot.retrieve_data(message.from_user.id, message.chat.id) as data:
        data['eng_word'] = eng_word
        data['rus_word'] = rus_word
        data['other_words'] = other_words


@bot.message_handler(func=lambda message: message.text == Command.SHOW_WORDS)
def show_words(message: types.Message) -> None:
    """
    Обрабатывает команду SHOW_WORDS.
    Показывает список изучаемых слов.

    :param message: Сообщение от пользователя.
    """
    chat_id = message.chat.id
    conn = psycopg2.connect(database=database, user=user, password=password)
    cur = conn.cursor()

    try:
        user_id = get_user_id(chat_id)
        cur.execute("""
            SELECT w.eng_word
            FROM words w
            LEFT JOIN user_words uw ON w.word_id = uw.word_id
            WHERE uw.user_id IS NULL
                    OR (uw.user_id = %s AND NOT uw.is_deleted)
                    OR (uw.user_id != %s AND uw.is_deleted AND NOT EXISTS (
                        SELECT 1
                        FROM user_words uw2
                        WHERE uw2.word_id = w.word_id
                        AND uw2.user_id = %s
                        AND uw2.is_deleted
                    ))
        """, (user_id, user_id, user_id))
        words = [row[0] for row in cur.fetchall()]
        bot.send_message(chat_id, show_hint(*words))
    except Exception as e:
        print(f"Ошибка: {e}")
        bot.send_message(chat_id, "Произошла ошибка при получении слов.")
    finally:
        cur.close()
        conn.close()


@bot.message_handler(func=lambda message: message.text == Command.NEXT)
def next_cards(message: types.Message) -> None:
    """
    Обрабатывает команду NEXT.
    Создает следующие карточки с английскими словами и командами.

    :param message: Сообщение от пользователя.
    """
    create_cards(message)


@bot.message_handler(func=lambda message: message.text == Command.DELETE_WORD)
def delete_word(message: types.Message) -> None:
    """
    Обрабатывает команду DELETE_WORD.
    Удаляет слово из изучаемых для конкретного пользователя из БД.

    :param message: Сообщение от пользователя.
    """
    chat_id = message.chat.id
    conn = psycopg2.connect(database=database, user=user, password=password)
    cur = conn.cursor()

    try:
        with bot.retrieve_data(message.from_user.id, chat_id) as data:
            cur.execute('SELECT word_id FROM words WHERE eng_word = %s', (data['eng_word'],))
            word_id = cur.fetchone()[0]
            user_id = get_user_id(chat_id)
            cur.execute('INSERT INTO user_words (user_id, word_id, is_deleted) VALUES (%s, %s, TRUE)',
                        (user_id, word_id))
            conn.commit()
            bot.send_message(chat_id, 'Слово успешно удалено!')
    except Exception as e:
        print(f"Ошибка: {e}")
        bot.send_message(chat_id, "Произошла ошибка при удалении слова.")
    finally:
        cur.close()
        conn.close()


@bot.message_handler(func=lambda message: message.text == Command.ADD_WORD)
def add_word(message: types.Message) -> None:
    """
    Обрабатывает команду ADD_WORD.
    Запрашивает у пользователя слово на русском и его перевод на английский.

    :param message: Сообщение от пользователя.
    """
    chat_id = message.chat.id
    bot.send_message(chat_id,
                     'Введите слово на русском и его перевод на английский через пробел (например, "Зеленый Green"): ')
    bot.set_state(message.from_user.id, MyStates.rus_word, message.chat.id)


@bot.message_handler(state=MyStates.rus_word)
def add_word_process(message: types.Message) -> None:
    """
    Обрабатывает ввод пользователя после команды ADD_WORD.
    Добавляет слово в изучаемые для конкретного пользователя в БД.

    :param message: Сообщение от пользователя.
    """
    chat_id = message.chat.id
    conn = psycopg2.connect(database=database, user=user, password=password)
    cur = conn.cursor()

    try:
        rus_word, eng_word = message.text.split()
        cur.execute('INSERT INTO words (rus_word, eng_word) VALUES (%s, %s) RETURNING word_id', (rus_word, eng_word))
        word_id = cur.fetchone()[0]
        user_id = get_user_id(chat_id)
        cur.execute('INSERT INTO user_words (user_id, word_id) VALUES (%s, %s)', (user_id, word_id))
        conn.commit()
        bot.send_message(chat_id, 'Слово успешно добавлено!')
    except ValueError:
        bot.send_message(chat_id, 'Неверный формат ввода. Попробуйте еще раз.')
    except Exception as e:
        print(f"Ошибка: {e}")
        bot.send_message(chat_id, "Произошла ошибка при добавлении слова.")
    finally:
        cur.close()
        conn.close()
        bot.delete_state(message.from_user.id, chat_id)


@bot.message_handler(func=lambda message: True, content_types=['text'])
def message_reply(message: types.Message) -> None:
    """
    Обрабатывает текстовые сообщения от пользователя.
    Проверяет, правильно ли пользователь выбрал перевод слова.

    :param message: Сообщение от пользователя.
    """
    chat_id = message.chat.id
    text = message.text
    markup = types.ReplyKeyboardMarkup(row_width=2)

    try:
        with bot.retrieve_data(message.from_user.id, message.chat.id) as data:
            eng_word = data['eng_word']
            if text == eng_word:
                hint = show_translate(data)
                hint_text = ['Отлично!❤', hint]
                buttons = [
                    types.KeyboardButton(Command.SHOW_WORDS),
                    types.KeyboardButton(Command.NEXT),
                    types.KeyboardButton(Command.ADD_WORD),
                    types.KeyboardButton(Command.DELETE_WORD)
                ]
                hint = show_hint(*hint_text)
            else:
                buttons = [types.KeyboardButton(word) for word in data['other_words']]
                buttons.append(types.KeyboardButton(eng_word))
                random.shuffle(buttons)
                buttons.extend([
                    types.KeyboardButton(Command.SHOW_WORDS),
                    types.KeyboardButton(Command.NEXT),
                    types.KeyboardButton(Command.ADD_WORD),
                    types.KeyboardButton(Command.DELETE_WORD)
                ])
                hint = show_hint('Допущена ошибка!', f'Попробуй ещё раз вспомнить слово 🇷🇺{data["rus_word"]}')
        markup.add(*buttons)
        bot.send_message(chat_id, hint, reply_markup=markup)
    except KeyError:
        bot.send_message(chat_id, 'Начните с команды /start или /cards. Попробуйте еще раз.')


bot.add_custom_filter(custom_filters.StateFilter(bot))

bot.infinity_polling(skip_pending=True)
