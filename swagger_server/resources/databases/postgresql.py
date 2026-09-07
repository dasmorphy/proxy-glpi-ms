from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, registry
from sqlalchemy.engine import url
from swagger_server.config.access import access


class PostgreSQLClient:

    def __init__(self, db: str):
        self.db = db

        credentials_db = PostgreSQLClient.get_credentials(self.db)

        driver = "postgresql+psycopg2"

        db_url = url.URL.create(
            drivername=driver,
            username=credentials_db["USER"],
            password=credentials_db["PASSWORD"],
            host=credentials_db["HOST"],
            port=credentials_db["PORT"],
            database=credentials_db["DB"],
        )

        self.engine = create_engine(
            db_url,
            echo=False,
            pool_pre_ping=True,
            pool_recycle=300
        )

        self.session_factory = sessionmaker(
            bind=self.engine,
            expire_on_commit=True
        )

        self.mapper_registry = registry()

    @staticmethod
    def get_credentials(db: str) -> dict:
        response_json = access()
        credentials_db = response_json["DB"][db]

        return {
            "HOST": credentials_db["HOST"],
            "DB": credentials_db["DB"],
            "USER": credentials_db["USER"],
            "PASSWORD": credentials_db["PASSWORD"],
            "PORT": credentials_db["PORT"],
        }
