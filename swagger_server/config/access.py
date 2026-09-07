import os
from dotenv import load_dotenv

load_dotenv()

def access():
    return {
        "DB": {
            "POSTGRESQL": {
                "USER": os.getenv('POSTGRESQL_USER'),
                "PASSWORD": os.getenv('POSTGRESQL_PASSWORD').strip("'"),
                "HOST": os.getenv('POSTGRESQL_HOST'),
                "PORT": os.getenv('POSTGRESQL_PORT'),
                "DB": os.getenv('POSTGRESQL_DB')
            },
            "REDIS": {
                "HOST": os.getenv('REDIS_HOST'),
                "PORT": os.getenv('REDIS_PORT'),
            },
            "SQLALCHEMY_ENGINE_OPTIONS": {
                "echo": False,
                "pool_recycle": 300,
                "pool_pre_ping": True
            }
        },
        "PASSWORDS": {
            "ENCRYPTION": os.getenv('ENCRYPTION').strip("'")
        },
        "GLPI": {
            "API": os.getenv("API_GLPI"),
            "APP_TOKEN": os.getenv("APP_TOKEN"),
            "USER_TOKEN_SESSION": os.getenv("USER_TOKEN_SESSION"),
            "TIMEOUT": float(os.getenv("GLPI_TIMEOUT", "30")),
        },
    }


def access_mode():
    return access()
