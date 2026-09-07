from swagger_server.config.access import access
import redis

class RedisClient:
    def __init__(self):
        credentials_db = RedisClient.get_credentials()
        self.client = redis.Redis(host=credentials_db["HOST"], port=credentials_db["PORT"], decode_responses=True)


    @staticmethod
    def get_credentials() -> dict:
        response_json = access()
        credentials_db = response_json["DB"]["REDIS"]

        return {
            "HOST": credentials_db["HOST"],
            "PORT": credentials_db["PORT"],
        }
