from sqlalchemy import create_engine  # , MetaData
from sqlalchemy.orm import sessionmaker, DeclarativeBase, Session  # , Mapped
from typing import Any
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

SessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=engine, expire_on_commit=False
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# class Base(DeclarativeBase):
#     # metadata = MetaData(schema="public")
#     pass


class BaseModelMixin(DeclarativeBase):
    """
    Base repository class that wraps CRUD methods plus some other useful stuff.
    """

    __abstract__ = True  # This tells SQLAlchemy not to create a table for this class
    # id: Mapped[int]

    @classmethod
    def get_by_id(cls, id: str, db_session: Session):
        """
        @brief Gets an object by identifier
        @param id  The identifier
        @param session The session
        @return The object by identifier or None if not found.
        """
        obj = db_session.get(cls, id)
        return obj

    @classmethod
    def get_all(cls, db_session: Session) -> list:
        """
        @brief Gets all objects
        @param session The session
        @return All objects
        """
        try:
            return db_session.query(cls).order_by(cls.id).all()
        except Exception:
            return db_session.query(cls).all()

    @classmethod
    def get_limit(cls, db_session: Session, limit: int = 100) -> list:
        """
        @brief Gets all objects
        @param session The session
        @return All objects
        """
        try:
            return db_session.query(cls).limit(limit).order_by(cls.id).all()
        except Exception:
            return db_session.query(cls).limit(limit).all()

    @classmethod
    def get_count(cls, db_session: Session) -> int:
        """
        @brief Gets the count of objects
        @param session The session
        @return The count of objects
        """
        return db_session.query(cls).count()

    @classmethod
    def exists(cls, id: int, db_session: Session) -> bool:
        """
        @brief Determines if the given object exists.
        @param id  The identifier.
        @param session The session
        @return True if it exists, false if not
        """
        return bool(db_session.query(cls).filter_by(id=id).count())

    @classmethod
    def exists_cls(cls, db_session: Session) -> bool:
        """
        @brief Determines if the given object exists
        @param session The session
        @return True if it exists, false if not
        """
        return bool(db_session.query(cls).count())

    @classmethod
    def create(cls, db_session: Session, **kwargs):
        """
        @brief Creates an object
        @param session database session
        @param kwargs arguments
        @return The new object
        """
        kwargs.pop("_sa_instance_state", None)
        obj = cls(**kwargs)
        db_session.add(obj)
        db_session.commit()
        db_session.refresh(obj)
        return obj

    @classmethod
    def update(cls, db_session: Session, id: str, **kwargs):
        """
        @brief Updates the given object
        @param session database session
        @param id identifier
        @param kwargs arguments
        @return object if it succeeds, None if it fails
        """
        obj = cls.get_by_id(id, db_session)
        if obj is None:
            return None

        for key, value in kwargs.items():
            setattr(obj, key, value)
        db_session.commit()
        db_session.refresh(obj)
        return obj

    @classmethod
    def delete(cls, db_session: Session, id: str):
        """
        @brief Deletes the given object
        @param session database session
        @param id identifier
        @return object if it succeeds, None if it fails
        """
        obj = cls.get_by_id(id, db_session)
        if obj is None:
            return None
        db_session.delete(obj)
        db_session.commit()
        return obj

    @classmethod
    def get_by_param(cls, db_session: Session, param_name: str, param_value: Any):
        """
        @brief Gets an object by identifier
        @warning This method might not work
        @param db session The session
        @param param_name Name of the parameter to search
        @param param_value Value of the parameter to search
        @return The object by identifier or None if not found
        """
        column = getattr(cls, param_name, None)
        if column is None:
            return None
        obj = db_session.query(cls).filter(column == param_value).first()
        return obj
