from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine

from app.all_models import Base
from app.config import get_settings

if context.config.config_file_name:
    fileConfig(context.config.config_file_name)

url = context.config.attributes.get("database_url") or get_settings().database_url
engine = create_engine(url)

with engine.connect() as connection:
    context.configure(connection=connection, target_metadata=Base.metadata)
    with context.begin_transaction():
        context.run_migrations()
