import asyncio
import logging
import sys
from os import getenv
from dotenv import load_dotenv
import httpx
from datetime import datetime, date, timedelta
from aiogram import Bot, Dispatcher, html, F, flags
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.filters import CommandStart
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton

load_dotenv()
TOKEN = getenv("BOT_TOKEN")
dp = Dispatcher()
scheduler = AsyncIOScheduler()
API_BASE_URL = "http://localhost:8000"

main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Добавить задачу"), KeyboardButton(text="Все задачи")],
        [KeyboardButton(text="Получить совет"), KeyboardButton(text="Я выполнил задачу")],
        [KeyboardButton(text="Удалить задания"), KeyboardButton(text="Профиль")],
    ],
    resize_keyboard=True,
    one_time_keyboard=False
)

addTask_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Описание"), KeyboardButton(text="Дедлайн")]
    ],
    resize_keyboard=True,
    one_time_keyboard=False
)


class AddTask(StatesGroup):
    waiting_for_description = State()
    waiting_for_deadline = State()

class getHelp(StatesGroup):
    waiting_for_id = State()

class TaskDone(StatesGroup):
    waiting_for_id = State()

class UserInfo(StatesGroup):
    get_user_info = State()

class DeleteTask(StatesGroup):
    waiting_for_id = State()



@dp.message(CommandStart())
async def command_start_handler(message: Message) -> None:
    if message.from_user is None:
        await message.answer("Не удалось определить пользователя ")
        return

    async with httpx.AsyncClient() as client:
        await client.post(
            f"{API_BASE_URL}/user/new/?tg_id={message.from_user.id}&name={message.from_user.full_name}"
        )


    await message.answer(html.bold("Добро пожаловать!") + "\n\nЯ помогу тебе с планированием дел\nТакже, я могу дать хороший совет по выполнению задачи 💡",
                         reply_markup=main_kb
                        )
    
    
@dp.message(F.text=="Добавить задачу")
async def add_task(message: Message, state: FSMContext):
    await message.answer(html.bold("Расскажи о своей задаче 📝"))
    await state.set_state(AddTask.waiting_for_description)


@dp.message(F.text=="Я выполнил задачу")
async def task_done(message: Message, state: FSMContext):
    await message.answer(html.bold("Введи номер задачи, которую ты выполнил "))
    await state.set_state(TaskDone.waiting_for_id)

@dp.message(F.text=="Профиль")
async def get_user_info(message: Message, state: FSMContext):
    if message.from_user is None:
        await message.answer("Не удалось определить пользователя")
        return


    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{API_BASE_URL}/tasks/user/?user_id={message.from_user.id}"
        )
    
    data = resp.json()

    await message.answer(html.bold(f"Всего задач: {data['total']}") + "\n\n" + html.bold(f"Выполнено: {data['done']} ✅") + "\n" +html.bold(f"Не выполнено: {data['incomplete']} ❌"))
    await state.clear()



@dp.message(TaskDone.waiting_for_id)
async def change_status(message: Message, state: FSMContext):
    if message.from_user is None:
        await message.answer("Не удалось определить пользователя")
        return
    
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{API_BASE_URL}/tasks/count/{message.from_user.id}",
            timeout=10.0
        )

    data = resp.json()
    max_id = data['max_id']

    if message.text is None:
        await message.answer("Введи номер задачи")
        return

    try:

        task_id = int(message.text)
        if task_id <= 0 or task_id > max_id:
            raise ValueError
    except ValueError:
        await message.answer(f"Задача номер {task_id} не существует\nВведите правильный номер")
        return
    
    if message.from_user is None:
        await message.answer("Не удалось определить пользователя")
        return


    async with httpx.AsyncClient() as client:
        resp = await client.put(
            f"{API_BASE_URL}/tasks/?user_id={message.from_user.id}&task_id={task_id}"
        )

    data = resp.json()
    scheduler.remove_job(f"reminder_{message.from_user.id}_{data['description']}")

    await message.answer(f"Задача номер {task_id}\n\n\"{data['description']}\"\n\nВыполнена успешно")
    await state.clear()






@dp.message(F.text == "Все задачи")
async def get_all_tasks(message: Message):
    if message.from_user is None:
        await message.answer("Не удалось определить пользователя")
        return
    
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{API_BASE_URL}/tasks/{message.from_user.id}",
            timeout=10.0,
        )

        allTasks = resp.json()
        result =""

    if len(allTasks) == 0:
        result = "У вас нет задач"
    else:
        for i, item in enumerate(allTasks):
            result += f"{i+1}\nЗадача: {item['description']}\nДедлайн: {item['deadline'][:10]}\n\n"

    await message.answer(result)



@dp.message(F.text == "Получить совет")
async def get_help(message: Message, state: FSMContext):
    if message.from_user is None:
        await message.answer("Не удалось определить пользователя")
        return
    
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{API_BASE_URL}/check_limit/?user_id={message.from_user.id}",
            timeout=10.0,
        )
    
    data = resp.json()

    if data['limit'] == 'bad':
        await message.answer("Лимит на получение советов: 5 запросов в день\nВы превысили лимит на сегодня, попробуйте завтра")
        return


    await message.answer("Введите номер задачи, чтобы получить совет")
    await state.set_state(getHelp.waiting_for_id)


@dp.message(getHelp.waiting_for_id)
async def get_AI_response(message: Message, state: FSMContext):
    if message.from_user is None:
        await message.answer("Не удалось определить пользователя")
        return
    
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{API_BASE_URL}/tasks/count/{message.from_user.id}",
            timeout=10.0
        )

    data = resp.json()
    maxId = int(data['max_id'])

    if message.text is None:
        await message.answer("Введите номер задачи")
        return

    try:
        task_id = int(message.text)
        if task_id <= 0 or task_id > int(maxId):
            raise ValueError
    except ValueError:
        await message.answer(f"Задача с номером {message.text} не существует\nВведите правильный номер")
        return
    
    
    
    loading_msg = await message.answer("Готовлю совет...")

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{API_BASE_URL}/sonar/?user_id={message.from_user.id}&task_id={task_id}",
            timeout=30.0
        )

    if resp.status_code == 202:
        async with httpx.AsyncClient() as client:
            await client.put(
                f"{API_BASE_URL}/new_request/?user_id={message.from_user.id}",
                timeout=10.0
            )

        await loading_msg.edit_text("Совет готов!")
        advice = resp.json()
        await message.answer(advice)

    else:
        await loading_msg.edit_text("Ошибка. Попробуйте еще раз")
        await state.clear()
        return



@dp.message(AddTask.waiting_for_description)
async def receive_description(message: Message, state: FSMContext):
    desc = message.text

    await state.update_data(description=desc)

    await message.answer("Какой дедлайн у этой задачи?\nВведи количество дней:")
    await state.set_state(AddTask.waiting_for_deadline)

@dp.message(AddTask.waiting_for_deadline)
async def receive_deadline(message: Message, state: FSMContext):
    try:
        days=int(str(message.text))
        if days <= 0:
            raise ValueError
    except ValueError:
        await message.answer("Введите положительное количество дней: ")
        return
    await state.update_data(deadline=days)

    if message.from_user is None:
        await message.answer("Не удалось определить пользователя")
        return

    data = await state.get_data()
    description = data["description"]
    deadline = data["deadline"]
    user_id = message.from_user.id

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{API_BASE_URL}/tasks/",
            json={
                "description": description,
                "deadline": days,
                "tg_id": user_id,
            },
            timeout=10.0,
        )

    if resp.status_code != 201:
        await message.answer("Не удалось создать задачу, попробуйте снова")
        await state.clear()
        return
    
    task = resp.json()
    dt = datetime.now().replace(microsecond=0) + timedelta(days=deadline) - timedelta(days=1)
    async def remind():
        await message.answer(f"Дедлайн уже через 24 часа\n\nОписание: {task['deadline']}")


    scheduler.add_job(
        remind,
        "date",
        run_date=dt,
        id=f"reminder_{message.from_user.id}_{task['description']}"
    )
    
    
    await message.answer(
        f"Описание: {task['description']}\n"
        f"Дедлайн: {task['deadline']} дня\n\n"
        f"Задача добавлена"
    )

    await state.clear()



@dp.message(F.text=="Удалить задания")
async def get_to_delete_task(message: Message, state: FSMContext):

    await message.answer("Введите номера заданий, которые вы хотите удалить, через запятую (1,2,3)\nЛибо просто одну цифру")
    await state.set_state(DeleteTask.waiting_for_id)

@dp.message(DeleteTask.waiting_for_id)
async def delete_task(message: Message, state: FSMContext):
    if message.from_user is None:
        await message.answer("Не удадось определить пользователя")
        return
    

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{API_BASE_URL}/tasks/{message.from_user.id}",
            timeout=10.0
        )

    tasks = resp.json()



    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{API_BASE_URL}/tasks/count/{message.from_user.id}",
            timeout=10.0
        )

    max_id = resp.json()["max_id"]
    tasks_to_delete = []
    tasks_to_delete_DB_id = []
    deleted = []
    not_deleted = []



    if message.text is None:
        await message.answer("Сообщение не получено")
        return
    
    try:
        for i in message.text.strip().split(","):
            if int(i) > 0 and int(i) <= max_id:
                tasks_to_delete.append(int(i))
            else: 
                not_deleted.append(int(i))
 
    except ValueError:
        await message.answer("Введите номера в правильном виде (1,2,3)")
        return
    

    for i, item in enumerate(tasks):
        if i+1 in tasks_to_delete:
            tasks_to_delete_DB_id.append(item["id"])






    
    for i in tasks_to_delete_DB_id:
        async with httpx.AsyncClient() as client:
            await client.delete(
                f"{API_BASE_URL}/tasks/delete/?item_id={i}",
                timeout=10.0
            )

    await message.answer(f"Удалены задания с номером: {tasks_to_delete}\nНе получилось удалить: {not_deleted}")
    await state.clear()



    


       




async def main() -> None:
    if TOKEN is None:
        raise RuntimeError("BOT_TOKEN is not set in environment")

    bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    scheduler.start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())
