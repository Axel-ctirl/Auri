# Migrations

Bread creates its schema on startup with `init_db()`, which runs `create_all`
and then adds any **nullable** column a newer version expects on an older
database file. That covers the common case of a table gaining a field.

Alembic is for everything else: renaming a column, changing a type, dropping
something, or backfilling data. Reach for it when `init_db()` cannot express the
change.

```bash
cd backend
alembic revision --autogenerate -m "rename messages.error to messages.failure"
# read the generated file before running it; autogenerate is a draft
alembic upgrade head
alembic downgrade -1
```

`env.py` reads the database URL from Bread's settings, so migrations follow
`BREAD_DATABASE_URL` and `BREAD_DATA_DIR` and always target the same file the
server uses.

`render_as_batch` is on because SQLite cannot alter most things in place;
Alembic rebuilds the table around the change instead. Back up `data/bread.db`
before running a migration you have not tested.
