from alembic import context

from app.core.database import engine

with engine.begin() as connection:
    context.configure(connection=connection)
    context.run_migrations()
