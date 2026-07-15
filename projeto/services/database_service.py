from pathlib import Path

import duckdb


class DatabaseService:
    BASE_DIR = Path(__file__).resolve().parent.parent
    DATABASE_PATH = BASE_DIR / "database" / "cnpj_hunter.duckdb"
    SCHEMA_PATH = BASE_DIR / "database" / "schema.sql"

    @classmethod
    def initialize_database(cls) -> None:
        cls.DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with duckdb.connect(str(cls.DATABASE_PATH)) as connection:
            if cls.SCHEMA_PATH.exists():
                schema = cls.SCHEMA_PATH.read_text(encoding="utf-8")
                connection.execute(schema)

    @classmethod
    def table_exists(cls, table_name: str) -> bool:
        with duckdb.connect(str(cls.DATABASE_PATH)) as connection:
            result = connection.execute(
                "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = ?",
                [table_name.lower()],
            ).fetchone()
            return result[0] > 0

    @classmethod
    def get_connection(cls):
        return duckdb.connect(str(cls.DATABASE_PATH))
