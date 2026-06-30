from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool, text

from app.config import get_settings
from app.database import Base
from app import models  # noqa: F401


config = context.config
config.set_main_option("sqlalchemy.url", get_settings().sqlalchemy_database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def ensure_version_table_width(connection) -> None:
    if connection.dialect.name != "postgresql":
        return
    connection.execute(
        text(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name = 'alembic_version'
                      AND column_name = 'version_num'
                      AND character_maximum_length < 255
                ) THEN
                    ALTER TABLE alembic_version
                    ALTER COLUMN version_num TYPE VARCHAR(255);
                END IF;
            END $$;
            """
        )
    )


def run_migrations_offline() -> None:
    context.configure(
        url=get_settings().sqlalchemy_database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        ensure_version_table_width(connection)
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
