import os
import psycopg2
from psycopg2.extras import RealDictCursor, execute_batch

class QueryResult:
    def __init__(self, data=None, count=None):
        self.data = data if data is not None else []
        self.count = count

class TableQuery:
    def __init__(self, conn_func, table_name):
        self.conn_func = conn_func
        self.table_name = table_name
        self.action = "SELECT"
        self.columns = "*"
        self.count_mode = None
        self.conditions = []
        self.params = []
        self.order_by = None
        self.limit_val = None
        self.payload = None
        self.on_conflict = None

    def select(self, columns="*", count=None):
        self.action = "SELECT"
        self.columns = columns
        self.count_mode = count
        return self

    def insert(self, data):
        self.action = "INSERT"
        self.payload = data if isinstance(data, list) else [data]
        return self

    def upsert(self, data, on_conflict=None):
        self.action = "UPSERT"
        self.payload = data if isinstance(data, list) else [data]
        self.on_conflict = on_conflict
        return self

    def update(self, data):
        self.action = "UPDATE"
        self.payload = data
        return self

    def delete(self):
        self.action = "DELETE"
        return self

    def eq(self, column, value):
        self.conditions.append(f"{column} = %s")
        self.params.append(value)
        return self

    def neq(self, column, value):
        self.conditions.append(f"{column} != %s")
        self.params.append(value)
        return self

    def in_(self, column, values):
        if not values:
            self.conditions.append("FALSE")
        else:
            placeholders = ", ".join(["%s"] * len(values))
            self.conditions.append(f"{column} IN ({placeholders})")
            self.params.extend(values)
        return self

    def ilike(self, column, pattern):
        self.conditions.append(f"{column} ILIKE %s")
        self.params.append(pattern)
        return self

    def is_(self, column, value):
        if value is None or str(value).lower() == "null":
            self.conditions.append(f"{column} IS NULL")
        else:
            self.conditions.append(f"{column} IS {value}")
        return self

    def order(self, column, desc=False):
        direction = "DESC" if desc else "ASC"
        self.order_by = f"{column} {direction}"
        return self

    def limit(self, n):
        self.limit_val = n
        return self

    def execute(self):
        conn = self.conn_func()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        try:
            where_clause = ""
            if self.conditions:
                where_clause = " WHERE " + " AND ".join(self.conditions)

            if self.action == "SELECT":
                cols = self.columns if self.columns != "*" else "*"
                sql = f"SELECT {cols} FROM {self.table_name}{where_clause}"
                if self.order_by:
                    sql += f" ORDER BY {self.order_by}"
                if self.limit_val:
                    sql += f" LIMIT {self.limit_val}"

                cur.execute(sql, tuple(self.params))
                rows = [dict(r) for r in cur.fetchall()]
                
                count_val = len(rows)
                if self.count_mode == "exact":
                    count_sql = f"SELECT COUNT(*) as total FROM {self.table_name}{where_clause}"
                    cur.execute(count_sql, tuple(self.params))
                    count_val = cur.fetchone()["total"]

                return QueryResult(data=rows, count=count_val)

            elif self.action == "INSERT":
                if not self.payload:
                    return QueryResult()
                keys = list(self.payload[0].keys())
                col_names = ", ".join(keys)
                placeholders = ", ".join(["%s"] * len(keys))
                sql = f"INSERT INTO {self.table_name} ({col_names}) VALUES ({placeholders})"
                val_tuples = [tuple(row.get(k) for k in keys) for row in self.payload]
                execute_batch(cur, sql, val_tuples, page_size=200)
                return QueryResult(data=self.payload)

            elif self.action == "UPSERT":
                if not self.payload:
                    return QueryResult()
                keys = list(self.payload[0].keys())
                col_names = ", ".join(keys)
                placeholders = ", ".join(["%s"] * len(keys))
                conflict_col = self.on_conflict or keys[0]
                
                conflict_targets = [c.strip() for c in conflict_col.split(",")]
                conflict_clause = ", ".join(conflict_targets)

                update_cols = [k for k in keys if k not in conflict_targets]
                if update_cols:
                    update_assignments = ", ".join([f"{k} = EXCLUDED.{k}" for k in update_cols])
                    sql = f"INSERT INTO {self.table_name} ({col_names}) VALUES ({placeholders}) ON CONFLICT ({conflict_clause}) DO UPDATE SET {update_assignments}"
                else:
                    sql = f"INSERT INTO {self.table_name} ({col_names}) VALUES ({placeholders}) ON CONFLICT ({conflict_clause}) DO NOTHING"
                
                val_tuples = [tuple(row.get(k) for k in keys) for row in self.payload]
                execute_batch(cur, sql, val_tuples, page_size=200)
                return QueryResult(data=self.payload)

            elif self.action == "UPDATE":
                set_clauses = [f"{k} = %s" for k in self.payload.keys()]
                sql = f"UPDATE {self.table_name} SET {', '.join(set_clauses)}{where_clause}"
                all_params = list(self.payload.values()) + self.params
                cur.execute(sql, tuple(all_params))
                return QueryResult()

            elif self.action == "DELETE":
                sql = f"DELETE FROM {self.table_name}{where_clause}"
                cur.execute(sql, tuple(self.params))
                return QueryResult()

        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            raise e
        finally:
            cur.close()

class NeonPostgresClient:
    """Drop-in Supabase-compatible client for Neon PostgreSQL using psycopg2 with autocommit."""
    def __init__(self, database_url):
        self.database_url = database_url
        self._conn = None

    def get_connection(self):
        if self._conn is not None and not self._conn.closed:
            try:
                with self._conn.cursor() as cur:
                    cur.execute("SELECT 1")
            except Exception:
                try:
                    self._conn.close()
                except Exception:
                    pass
                self._conn = None

        if self._conn is None or self._conn.closed:
            self._conn = psycopg2.connect(self.database_url)
            self._conn.autocommit = True
        return self._conn

    def table(self, table_name):
        return TableQuery(self.get_connection, table_name)
