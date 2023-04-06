from tortoise import Tortoise


async def init():
    config = {
        "connections": {
            "default": {
                "engine": "tortoise.backends.asyncpg",
                "credentials": {
                    "host": "localhost",
                    "port": "5432",
                    "user": "postgres",
                    "password": "rat",
                    "database": "postgres"
                }
            }
        },
        "apps": {
            "models": {
                "models": ["database.models"],
                "default_connection": "default"
            }
        }
    }
    await Tortoise.init(config=config)
    await Tortoise.generate_schemas()
