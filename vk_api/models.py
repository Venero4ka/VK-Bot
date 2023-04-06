import enum
import inspect
import json
from datetime import datetime
from typing import TYPE_CHECKING, Dict, Any
from pydantic import BaseModel
if TYPE_CHECKING:
    from .api_handler import APIHandlerBase


class Message(BaseModel):
    id: int
    user: 'User'
    date: datetime
    text: str
    payload: Dict[str, Any]

    def __init__(self, **kwargs):
        date = kwargs.get("date", 0)
        payload = kwargs.get("payload")

        payload = json.loads(payload) if payload is not None else {"command": None}
        date = datetime.fromtimestamp(date)
        kwargs.update({"date": date, "payload": payload})
        super(Message, self).__init__(**kwargs)

    async def replay(self, message_text: str = "", *, reply: bool = False, handler: 'APIHandlerBase', **kwargs):
        reply_to = self.id if reply is True else ""
        await handler.send_message(message_text, user_id=self.user.id, reply_to=reply_to, **kwargs)


class Keyboard:
    def __init__(self, *, one_time: bool = True):
        self.keyboard = {
            "one_time": one_time,
            "buttons": []
        }

    def add_button_to_row(self, label: str, *, color: 'Colors' = None, command: str = "",
                          btn_type: str = "text", row_index: int = 0):
        if color is None:
            color = self.Colors.PRIMARY
        keyboard_buttons = self.keyboard["buttons"]
        button = {
            "action": {
                "type": btn_type,
                "payload": {"command": command},
                "label": label
            },
            "color": color.value
        }
        if len(keyboard_buttons) <= row_index:
            not_enough_row_count = row_index + 1 - len(keyboard_buttons)
            for _ in range(not_enough_row_count):
                keyboard_buttons.append([])
        keyboard_buttons[row_index].append(button)
    
    def __call__(self, *args, **kwargs):
        return str(json.dumps(self.keyboard))

    class Colors(enum.Enum):
        PRIMARY = "primary"
        SECONDARY = "secondary"
        POSITIVE = "positive"
        NEGATIVE = "negative"


class User(BaseModel):
    id: int
    first_name: str
    last_name: str
    screen_name: str
    sex: int = None
    status: str = None
    photo_id: str = None
    bdate: datetime = None
    city: dict = None
    country: dict = None
    relation: int = None
    about: str = None
    score: int = 0
    rate: int = 0

    def __init__(self, **kwargs):
        bdate = kwargs.get("bdate")
        if bdate:
            try:
                bdate = datetime.strptime(bdate, "%d.%m.%Y")
            except ValueError:
                bdate = datetime.strptime(bdate, "%d.%m")
        kwargs.update({"bdate": bdate})
        super(User, self).__init__(**kwargs)


for obj in locals().copy().values():
    if inspect.isclass(obj) and issubclass(obj, BaseModel):
        obj.update_forward_refs()
