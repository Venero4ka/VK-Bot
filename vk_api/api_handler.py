import asyncio
import os
import random
import signal
from typing import Coroutine

import aiohttp
from .events import MessageEvents, get_events_list_names
from .models import Message, User
from asyncio_throttle import Throttler


class APIHandlerBase:
    _instance = {}
    commands = {}
    throttler = Throttler(rate_limit=5)
    tasks: list[Coroutine] = []
    session: aiohttp.ClientSession

    VK_API_TOKEN: str
    VK_API_VERSION: str

    def __new__(cls, *args, **kwargs):
        if cls not in cls._instance:
            instance = super(APIHandlerBase, cls).__new__(cls)
            cls._instance[cls] = instance
            cls.VK_API_TOKEN: str = os.getenv("VK_API_TOKEN")
            cls.VK_API_VERSION: str = os.getenv("VK_API_VERSION")
            for event_list_names in get_events_list_names():
                for event_name in event_list_names:
                    cls.commands.update({event_name: []})
        return cls._instance[cls]

    @classmethod
    async def method(cls, method: str, **json_data) -> dict:
        async with cls.throttler:
            url = f"https://api.vk.com/method/{method}?access_token={cls.VK_API_TOKEN}&v={cls.VK_API_VERSION}"
            async with cls.session.get(url, params=json_data) as response:
                json_response = await response.json()
                error = json_response.get("error")
                data = json_response.get("response")
                if error or not data:
                    return await cls._error_handler(error, method, **json_data)
                return data

    @classmethod
    async def _error_handler(cls, error: dict, method: str, **json_data) -> dict | None:
        error_code = error.get("error_code")
        match error_code:
            case 6:  # Too many requests in second
                await asyncio.sleep(1)
                return await cls.method(method, **json_data)
            case 9:  # Flood control: too much messages sent to user
                return None
            case 38:
                return await cls.method(method, **json_data)
            case 100:
                print(error)
                cls.exit()
            case _:
                print(error)
                cls.exit()

    @classmethod
    def add_task(cls, *tasks: Coroutine):
        for task in tasks:
            cls.tasks.append(task)

    @classmethod
    async def complete_tasks(cls):
        await asyncio.gather(*cls.tasks)
        cls.tasks.clear()

    @classmethod
    def startup(cls):
        print("STARTUP FUNCTION")

    @classmethod
    def exit(cls, *_):
        print("EXIT FUNCTION")
        exit()

    @classmethod
    async def send_message(cls, message_text: str, *, user_id: int, **kwargs):
        random_id = random.randrange(2_147_483_647)
        await cls.method("messages.send", message=message_text, random_id=random_id, user_id=user_id, **kwargs)

    @classmethod
    async def get_user_by_id(cls, user_id: int) -> User:
        fields = "last_seen,photo_id,personal,relation,screen_name,sex,status,about,bdate,city,country"
        response = await cls.method("users.get", user_ids=user_id, fields=fields)
        for user_data in response:
            return User.parse_obj(user_data)

    def command(self, event: str, **options):
        def decorator(func):
            if event in self.commands:
                self.commands[event].append([func, options])

            def wrapper(*args, **kwargs):
                return func(*args, **kwargs)
            return wrapper
        return decorator


class APIHandlerUser(APIHandlerBase):
    VK_API_TOKEN: str = os.getenv("VK_API_TOKEN_USER")

    def __new__(cls, *args, **kwargs):
        if cls not in cls._instance:
            super(APIHandlerUser, cls).__new__(cls)
            cls.VK_API_TOKEN = os.getenv("VK_API_TOKEN_USER")
        return cls._instance[cls]

    @classmethod
    async def method(cls, method: str, **json_data) -> dict:
        async with aiohttp.ClientSession() as session:
            cls.session = session
            return await super(APIHandlerUser, cls).method(method, **json_data)


class APIHandlerGroup(APIHandlerBase):
    VK_API_TOKEN: str
    VK_GROUP_ID: str

    KEY: str
    SERVER: str
    TS: str

    def __new__(cls, *args, **kwargs):
        if cls not in cls._instance:
            super(APIHandlerGroup, cls).__new__(cls)
            cls.VK_API_TOKEN = os.getenv("VK_API_TOKEN_GROUP")
            cls.VK_GROUP_ID: str = os.getenv("VK_GROUP_ID")
        return cls._instance[cls]

    @classmethod
    async def method(cls, method: str, **kwargs) -> dict:
        kwargs.update({"group_id": cls.VK_GROUP_ID})
        return await super(APIHandlerGroup, cls).method(method, **kwargs)

    @classmethod
    async def _set_long_poll_server(cls) -> None:
        response = await cls.method("groups.getLongPollServer")
        cls.KEY, cls.SERVER, cls.TS = response.get("key"), response.get("server"), response.get("ts")
        assert all((cls.KEY, cls.SERVER, cls.TS)), f"incorrect long poll, {cls.KEY=}, {cls.SERVER=}, {cls.TS=}"

    @classmethod
    async def _event_handler(cls, events: list):
        for event in events:
            obj: dict = event.get("object")
            event_type: str = event.get("type")
            match event_type:
                case MessageEvents.new_message:
                    message_data: dict = obj.get("message")
                    message_user = await cls.get_user_by_id(message_data.get("from_id"))
                    message: Message = Message(**message_data, user=message_user)
                    message_new_commands = cls.commands.get(MessageEvents.new_message, [])
                    for func, options in message_new_commands:
                        capture_messages = options.get("message", [])
                        capture_command = options.get("command", [])
                        buttons_commands = message.payload.values()
                        if not options:
                            cls.add_task(func(message))
                        elif message.text in capture_messages:
                            cls.add_task(func(message))
                        elif capture_command in buttons_commands:
                            cls.add_task(func(message))

                case _:
                    print("NOT SUPPORTED THIS EVENT TYPE:", event_type)

    @classmethod
    async def _listen(cls, wait=25):
        url = f"{cls.SERVER}?act=a_check&key={cls.KEY}&ts={cls.TS}&wait={wait}"
        async with cls.session.get(url) as response:
            json_response = await response.json()
            cls.TS = json_response.get("ts")
            events = json_response.get("updates")
            assert cls.TS is not None, f"incorrect ts, {json_response=}"
            assert events is not None, f"incorrect events, {json_response=}"
            await cls._event_handler(events)

    @classmethod
    async def run(cls):
        cls.startup()
        signal.signal(signal.SIGINT, cls.exit)

        async with aiohttp.ClientSession() as session:
            cls.session = session
            await cls._set_long_poll_server()
            while True:
                await cls._listen()
                await cls.complete_tasks()

    async def __aenter__(self):
        return await self._listen()


