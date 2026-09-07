"""Database connection and schema bootstrap for AWS Cost Analyzer.

Reads MySQL connection settings from environment variables:
    DB_HOST (default: 127.0.0.1)
    DB_PORT (default: 3306)
    DB_USER (default: root)
    DB_PASS (default: empty)
    DB_NAME (default: aws_costs)

The `initialize_tables()` function is invoked on FastAPI startup and is
idempotent — safe to call on every boot.
"""

from __future__ import annotations

import os
from typing import Optional  # noqa: F401  (kept for downstream imports)

import mysql.connector
from mysql.connector import errorcode


def _config() -> dict:
    return {
        "host": os.getenv("DB_HOST", "127.0.0.1"),
        "port": int(os.getenv("DB_PORT", "3306")),
        "user": os.getenv("DB_USER", "root"),
        "password": os.getenv("DB_PASS", ""),
        "database": os.getenv("DB_NAME", "aws_costs"),
        "autocommit": False,
    }


def _ensure_database(cursor) -> None:
    """Create the target database if it does not exist."""
    db_name = _config()["database"]
    cursor.execute(
        f"CREATE DATABASE IF NOT EXISTS `{db_name}` "
        "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
    )


def get_connection():
    """Return a new MySQL connection. Caller is responsible for close()."""
    cfg = _config().copy()
    database = cfg.pop("database")
    try:
        conn = mysql.connector.connect(**cfg, database=database)
    except mysql.connector.Error as err:
        # Database may not exist yet on first run — create it then retry.
        if err.errno == errorcode.ER_BAD_DB_ERROR:
            bootstrap = mysql.connector.connect(**cfg)
            cursor = bootstrap.cursor()
            try:
                _ensure_database(cursor)
            finally:
                cursor.close()
            bootstrap.close()
            conn = mysql.connector.connect(**cfg, database=database)
        else:
            raise
    return conn


_SCHEMA: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS cost_data (
        id           BIGINT       NOT NULL AUTO_INCREMENT,
        date         DATE         NULL,
        service      VARCHAR(128) NULL,
        region       VARCHAR(64)  NULL,
        usage_type   VARCHAR(128) NULL,
        cost         DECIMAL(18,4) NULL,
        PRIMARY KEY (id),
        KEY idx_cost_date (date),
        KEY idx_cost_service (service)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS cost_summary (
        date         DATE         NULL,
        service      VARCHAR(128) NULL,
        region       VARCHAR(64)  NULL,
        usage_type   VARCHAR(128) NULL,
        total_cost   DECIMAL(18,4) NULL,
        UNIQUE KEY uq_summary (date, service, region, usage_type)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
)


def initialize_tables() -> None:
    """Create cost_data and cost_summary if they don't exist. Idempotent."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        try:
            for stmt in _SCHEMA:
                cur.execute(stmt)
            conn.commit()
        finally:
            cur.close()
    finally:
        if conn.is_connected():
            conn.close()