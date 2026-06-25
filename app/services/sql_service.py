import datetime
import decimal
import json
import re
import uuid
from typing import Any

import psycopg2

from app.config import settings
from app.services.llm_service import generate
from app.services.query_cache_service import query_cache

# psycopg2 returns driver-native types (datetime, Decimal, UUID, bytes, ...) that
# json.dumps can't handle directly, so each value is normalized to a JSON-safe type
# before a row is returned to callers.
def _serialize_value(value: Any) -> Any:
    if isinstance(value, datetime.datetime):
        return value.isoformat()
    if isinstance(value, datetime.date):
        return value.isoformat()
    if isinstance(value, datetime.time):
        return value.isoformat()
    if isinstance(value, datetime.timedelta):
        return str(value)
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _serialize_row(row: dict[str, Any]) -> dict[str, Any]:
    """Serialize all values in a row dict for JSON compatibility."""
    return {k: _serialize_value(v) for k, v in row.items()}


def is_select_only(sql: str) -> bool:
    """Return True if the SQL is a SELECT statement only."""
    # This is the only safeguard before LLM-generated SQL is executed against the
    # real database, so it must reject anything that isn't a plain read.
    cleaned = sql.strip().lower()
    if not cleaned.startswith("select"):
        return False
    forbidden = ["insert", "update", "delete", "drop", "alter", "create", "truncate", "grant", "revoke"]
    for kw in forbidden:
        # \b word boundaries prevent false positives on identifiers that merely
        # contain a forbidden keyword as a substring, e.g. a column named "updated_at".
        if re.search(rf"\b{kw}\b", cleaned):
            return False
    return True



class SQLService:
    def __init__(self):
        self._schema_context: str | None = None

    def _build_schema_context(self) -> str:
        # Memoized per instance: the schema doesn't change within a process's
        # lifetime, so this avoids hitting information_schema on every SQL generation call.
        if self._schema_context is not None:
            return self._schema_context

        conn = psycopg2.connect(settings.database_url)
        cur = conn.cursor()
        cur.execute("""
            SELECT table_name, column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = 'public'
            ORDER BY table_name, ordinal_position;
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()


        tables: dict[str, list[str]] = {}
        for table, col, dtype in rows:
            tables.setdefault(table, []).append(f"{col} ({dtype})")

        lines = ["Database schema:"]
        for table, cols in tables.items():
            lines.append(f"  {table}: {', '.join(cols)}")

        self._schema_context = "\n".join(lines)
        return self._schema_context

    
    def generate_sql(self, question: str) -> dict:
        # Keyed on the natural-language question, separate from execute_sql's cache
        # (which keys on the generated SQL), so a repeated question skips the LLM
        # call even before any SQL text exists.
        cached = query_cache.get_sql_generation(question)
        if cached is not None:
            return {"sql": cached, "explanation": "Loaded from SQL generation cache."}

        schema = self._build_schema_context()
        system = (
            "You are a SQL expert. Given a database schema and a question, "
            "generate a valid PostgreSQL SELECT query. Return JSON with keys: sql, explanation."
        )
        user = f"{schema}\n\nQuestion: {question}\n\nReturn only the JSON."
        result = generate(system, user, model=settings.vanna_model, temperature=settings.vanna_temperature)
        text = result["text"]

        # The model is asked for raw JSON but still sometimes wraps it in a markdown
        # code fence; strip the fence lines so json.loads doesn't choke on them.
        text = text.strip()
        if text.startswith("```"):
            text = "\n".join(text.splitlines()[1:-1]).strip()
        data = json.loads(text)
        payload = {
            "sql": data.get("sql", ""),
            "explanation": data.get("explanation", ""),
        }

        query_cache.set_sql_generation(question, payload["sql"])
        return payload

    
    def execute_sql(self, sql: str) -> list[dict]:
        # Re-validated here (not just trusted from generate_sql) since callers may
        # pass in arbitrary SQL, e.g. a user-edited query, not only model output.
        if not is_select_only(sql):
            raise ValueError("Only SELECT statements are allowed")

        # Keyed on the exact SQL text, so identical queries skip the DB round-trip.
        cached = query_cache.get_sql_result(sql)
        if cached is not None:
            return cached

        conn = psycopg2.connect(settings.database_url)
        cur = conn.cursor()
        cur.execute(sql)
        columns = [desc[0] for desc in cur.description] if cur.description else []
        rows = cur.fetchall()
        cur.close()
        conn.close()

        # strict=True turns a columns/row length mismatch into an explicit error
        # instead of silently truncating data.
        result = [_serialize_row(dict(zip(columns, row, strict=True))) for row in rows]
        query_cache.set_sql_result(sql, result)
        return result

