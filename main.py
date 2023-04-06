import asyncio
from copy import copy

from database.config import init as init_database
from database.models import User as UserDB
from vk_api.api_handler import APIHandlerGroup, APIHandlerBase, APIHandlerUser
from dotenv import load_dotenv

from vk_api.models import Message, Keyboard, User
from vk_api.events import MessageEvents

load_dotenv()
APIHandlerBase()
ahu = APIHandlerUser()
ahg = APIHandlerGroup()

FOUNDED_USERS = []


async def get_users():
    filters_fields = {"has_photo": 1, "age_from": 18, "is_closed": 0}
    user_fields = "last_seen,photo_id,personal,relation,screen_name,sex,status,about,bdate,city,country"
    for status in [1, 6]:
        response = await ahu.method("users.search", status=status, count=1000, country=1, fields=user_fields,
                                    **filters_fields)
        for user_data in response["items"]:
            if user_data["is_closed"] is not True:
                user = User.parse_obj(user_data)
                FOUNDED_USERS.append(user)
                print("[INFO]", user.last_name, user.first_name, f"[https://vk.com/{user.screen_name}]", "добавлен")


async def get_most_liked_user_photos(user_id):
    response = await ahu.method("photos.getAll", owner_id=user_id, extended=1, count=100)
    photos = sorted(response["items"], key=lambda photo: photo["likes"]["count"], reverse=True)
    return [f"photo{user_id}_{photo['id']}" for photo in photos]


async def search(message: Message):
    user_suitable = await get_users_suitable(message.user)  # add var score into user object
    if not user_suitable:
        await message.replay("К сожалению для вас подходящих пользователей больше не найдено :(", handler=ahg)
        return
    birth_date, address = "", ""
    if user_suitable.bdate:
        birth_date = f"День рождения: {user_suitable.bdate.strftime('%d.%m.%Y')}\n"
    if user_suitable.country or user_suitable.city:
        country = user_suitable.country["title"] if user_suitable.country else ''
        city = user_suitable.city["title"] if user_suitable.city else ''
        address = f"Проживает: {country}{'/' if country and city else ''}{city}\n"
    photos = await get_most_liked_user_photos(user_suitable.id)
    description = (f"{user_suitable.first_name} {user_suitable.last_name}\n"
                   f"{user_suitable.status}\n" +
                   birth_date +
                   address +
                   # add var score into user object 21 line
                   f"Оценка: {user_suitable.rate:.1f}/5.0 (Рейтинг: {user_suitable.score:.1f})\n"
                   f"@id{user_suitable.id}")
    await message.replay(description, attachment=f"photo{user_suitable.photo_id}", handler=ahg)
    if photos:
        attachment = ','.join(photos[:3])
        await message.replay(attachment=attachment, handler=ahg)


async def get_users_suitable(target_user: User) -> User | None:
    user_target_db, _ = await UserDB.get_or_create(id=target_user.id)
    users_suitable = []
    for user in FOUNDED_USERS:
        if target_user.sex and user.sex == target_user.sex:
            continue
        user: User = copy(user)
        user.score = 0
        if user.status:
            user.score += .3
        if user.city:
            user.score += .3
            if target_user.city:
                if user.city == target_user.city:
                    user.score += 5
        if user.country:
            user.score += .1
            if target_user.country:
                if user.country == target_user.country:
                    user.score += 2.5
                else:
                    user.score -= 5
        if user.bdate:
            user.score += .3
            if target_user.bdate:
                if user.bdate.date == target_user.bdate.date:
                    user.score += 1.5
                elif user.bdate.year == target_user.bdate.year:
                    user.score += 1
        if user.about:
            user.score += .1
        if user.relation == 6:
            user.score += 2.5

        users_suitable.append(user)

    users_suitable.sort(key=lambda user: -user.score)
    scores = [user.score for user in users_suitable]
    score_max = max(scores)
    score_min = min(scores)
    for user in users_suitable:
        user_db = await user_target_db.already_sees.filter(id=user.id)
        if user_db:
            continue
        best_user_suitable = user
        break
    else:
        return
    best_user_suitable.rate = ((best_user_suitable.score - score_min) / (score_max - score_min)) * 5
    user_db, _ = await UserDB.get_or_create(id=user.id)
    await user_target_db.already_sees.add(user_db)
    return best_user_suitable


async def init():
    await get_users()
    await init_database()


@ahg.command(MessageEvents.new_message, message="start", command="start")
async def registration(message: Message):
    user = await UserDB.create_or_get_user_by_id(message.user.id)
    search_keyboard = Keyboard(one_time=False)
    search_keyboard.add_button_to_row("Поиск", command="search", color=search_keyboard.Colors.POSITIVE)
    await ahg.send_message("Нажми на кнопку Поиск, чтобы найти свою вторую половинку",
                           user_id=user.id, keyboard=search_keyboard())


@ahg.command(MessageEvents.new_message, command="search")
async def search_command(message: Message):
    await search(message)


if __name__ == '__main__':
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(init())
    loop.run_until_complete(ahg.run())
