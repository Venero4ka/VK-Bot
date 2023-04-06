from tortoise import fields, models


class User(models.Model):
    id = fields.IntField(pk=True)
    already_sees = fields.ManyToManyField("models.User", related_name="users")

    @classmethod
    async def create_or_get_user_by_id(cls, user_id: int | str) -> 'User':
        user, _ = await User.get_or_create(id=user_id)
        return user
