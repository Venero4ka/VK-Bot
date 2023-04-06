import enum
import inspect
import sys


class EventsClass(str, enum.Enum):
    @classmethod
    def get_values(cls):
        return [event for event in cls]


class MessageEvents(EventsClass):
    new_message = "message_new"


def get_events_list_names() -> list:
    classes_in_current_module = inspect.getmembers(sys.modules[__name__])
    for name, obj in classes_in_current_module:
        if inspect.isclass(obj) and issubclass(obj, EventsClass):
            yield obj.get_values()
