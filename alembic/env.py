import os
from logging.config import fileConfig
from alembic import context
from sqlalchemy import engine_from_config, pool
from app import models  # pozor: nesmí spouštět Pydantic Settings při importu

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = models.BaseModelMixin.metadata

def get_url() -> str:
    # 1) ENV (docker-compose .env)
    url = os.getenv("SQLALCHEMY_DATABASE_URL")
    # 2) fallback alembic.ini (sqlalchemy.url)
    if not url:
        url = config.get_main_option("sqlalchemy.url")
    if not url:
        raise RuntimeError("No DB URL. Set SQLALCHEMY_DATABASE_URL env or alembic.ini sqlalchemy.url")
    return url

def run_migrations_offline():
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online():
    # doplň URL do konfigu pro engine_from_config
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = get_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
