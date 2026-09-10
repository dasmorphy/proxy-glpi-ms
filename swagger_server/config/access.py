import os
from dotenv import load_dotenv

load_dotenv()

def access():
    return {
        "DB": {
            "TELEARSEG": {
                "USER": os.getenv('TELEARSEG_USER'),
                "PASSWORD": os.getenv('TELEARSEG_PASSWORD').strip("'"),
                "HOST": os.getenv('TELEARSEG_HOST'),
                "PORT": os.getenv('TELEARSEG_PORT'),
                "DB": os.getenv('TELEARSEG_DB')
            },
            "ZENTINEL": {
                "USER": os.getenv('ZENTINEL_USER'),
                "PASSWORD": os.getenv('ZENTINEL_PASSWORD').strip("'"),
                "HOST": os.getenv('ZENTINEL_HOST'),
                "PORT": os.getenv('ZENTINEL_PORT'),
                "DB": os.getenv('ZENTINEL_DB')
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
        "GLPI": {
            "API": os.getenv("API_GLPI"),
            "APP_TOKEN": os.getenv("APP_TOKEN"),
            "USER_TOKEN_SESSION": os.getenv("USER_TOKEN_SESSION"),
            "TIMEOUT": float(os.getenv("GLPI_TIMEOUT", "30")),
        },
    }


def access_mode():
    return access()
