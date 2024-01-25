from sqlalchemy import create_engine, MetaData
from sqlalchemy.orm import sessionmaker, DeclarativeBase
import os

SQLALCHEMY_DATABASE_URL = os.getenv("SQLALCHEMY_DATABASE_URL")
if SQLALCHEMY_DATABASE_URL is None:
    raise ValueError("$SQLALCHEMY_DATABASE_URL is not defined")

if "sqlite" in SQLALCHEMY_DATABASE_URL:
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        connect_args={
            "check_same_thread": False
        },  # ...is needed only for SQLite. It's not needed for other databases.
    )
else:
    engine = create_engine(SQLALCHEMY_DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class Base(DeclarativeBase):
    metadata = MetaData(schema="public")
