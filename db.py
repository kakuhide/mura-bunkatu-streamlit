from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

from config import DATABASE_URL


def get_engine():
    return create_engine(
        DATABASE_URL,
        poolclass=NullPool,
        future=True,
        connect_args={
            "sslmode": "require",
            "options": "-c search_path=public,extensions",
        },
    )