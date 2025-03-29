"""
Database utility functions to standardize database operations.
"""

import sqlite3
import os
import logging
from typing import List, Dict, Any, Optional, Tuple, Callable, Union
import datetime

from app.constants import (
    DATABASE_PATH, TABLE_RECORDINGS, FIELD_ID, FIELD_FILENAME, FIELD_FILE_PATH,
    FIELD_DATE_CREATED, FIELD_DURATION, FIELD_RAW_TRANSCRIPT, FIELD_PROCESSED_TEXT,
    FIELD_RAW_TRANSCRIPT_FORMATTED, FIELD_PROCESSED_TEXT_FORMATTED
)

# Configure logging
logger = logging.getLogger('transcribrr')


def ensure_database_exists() -> None:
    """Ensure the database and required tables exist."""
    conn = None
    try:
        conn = get_connection()
        # Ensure tables from all features exist
        create_recordings_table(conn)
        # Note: FolderManager currently initializes its own tables directly.
        # Consider moving folder table creation here for consistency.
        # create_folders_table(conn)
        # create_recording_folders_table(conn)
        logger.debug("Database structure verified/initialized successfully")
    except Exception as e:
        logger.error(f"Error initializing database structure: {e}", exc_info=True)
        raise
    finally:
        if conn:
            conn.close()

# --- Connection ---
def get_connection() -> sqlite3.Connection:
    """Get a connection to the SQLite database."""
    db_dir = os.path.dirname(DATABASE_PATH)
    os.makedirs(db_dir, exist_ok=True) # Ensure directory exists
    try:
        # Consider adding timeout parameter: sqlite3.connect(DATABASE_PATH, timeout=10)
        conn = sqlite3.connect(DATABASE_PATH)
        conn.execute("PRAGMA foreign_keys = ON")
        return conn
    except sqlite3.Error as e:
        logger.critical(f"FATAL: Failed to connect to database at {DATABASE_PATH}: {e}", exc_info=True)
        raise RuntimeError(f"Could not connect to database: {e}")

# --- Table Creation ---
def create_recordings_table(conn: sqlite3.Connection) -> None:
    """Create the recordings table if it doesn't exist."""
    sql_create_recordings_table = f"""
    CREATE TABLE IF NOT EXISTS {TABLE_RECORDINGS} (
        {FIELD_ID} INTEGER PRIMARY KEY AUTOINCREMENT,
        {FIELD_FILENAME} TEXT NOT NULL,
        {FIELD_FILE_PATH} TEXT NOT NULL UNIQUE, -- Added UNIQUE constraint
        {FIELD_DATE_CREATED} TEXT NOT NULL,
        {FIELD_DURATION} TEXT, -- Allow NULL initially
        {FIELD_RAW_TRANSCRIPT} TEXT,
        {FIELD_PROCESSED_TEXT} TEXT,
        {FIELD_RAW_TRANSCRIPT_FORMATTED} BLOB,
        {FIELD_PROCESSED_TEXT_FORMATTED} BLOB
    );
    """
    # Add Index for faster lookups by path
    sql_create_filepath_index = f"""
    CREATE INDEX IF NOT EXISTS idx_recording_filepath ON {TABLE_RECORDINGS} ({FIELD_FILE_PATH});
    """
    try:
        cursor = conn.cursor()
        cursor.execute(sql_create_recordings_table)
        cursor.execute(sql_create_filepath_index)
        conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Error creating recordings table or index: {e}", exc_info=True)
        raise

# --- CRUD Operations for Recordings ---
def get_all_recordings(conn: sqlite3.Connection) -> List[Tuple]:
    """Get all recordings, ordered by date descending."""
    try:
        cursor = conn.cursor()
        cursor.execute(f"SELECT * FROM {TABLE_RECORDINGS} ORDER BY {FIELD_DATE_CREATED} DESC")
        return cursor.fetchall()
    except sqlite3.Error as e:
        logger.error(f"Error getting all recordings: {e}", exc_info=True)
        raise

def get_recording_by_id(conn: sqlite3.Connection, recording_id: int) -> Optional[Tuple]:
    """Get a recording by its ID."""
    try:
        cursor = conn.cursor()
        cursor.execute(f"SELECT * FROM {TABLE_RECORDINGS} WHERE {FIELD_ID}=?", (recording_id,))
        return cursor.fetchone()
    except sqlite3.Error as e:
        logger.error(f"Error getting recording {recording_id}: {e}", exc_info=True)
        raise

def create_recording(conn: sqlite3.Connection, recording_data: Tuple) -> int:
    """Create a new recording."""
    # Expects (filename, file_path, date_created, duration, raw_transcript, processed_text)
    # Ensure date_created is in correct format 'YYYY-MM-DD HH:MM:SS'
    if len(recording_data) < 4:
         raise ValueError("Recording data must contain at least filename, file_path, date_created, duration")

    # Pad with defaults if transcript/processed text are missing
    data_to_insert = list(recording_data)
    while len(data_to_insert) < 6:
        data_to_insert.append(None) # Use None for missing transcript/processed

    sql = f"""INSERT INTO {TABLE_RECORDINGS}(
        {FIELD_FILENAME}, {FIELD_FILE_PATH}, {FIELD_DATE_CREATED},
        {FIELD_DURATION}, {FIELD_RAW_TRANSCRIPT}, {FIELD_PROCESSED_TEXT}
    ) VALUES(?,?,?,?,?,?)"""

    try:
        cursor = conn.cursor()
        cursor.execute(sql, tuple(data_to_insert[:6])) # Insert first 6 elements
        conn.commit()
        new_id = cursor.lastrowid
        logger.info(f"Created recording '{data_to_insert[0]}' with ID {new_id}")
        return new_id
    except sqlite3.IntegrityError as e:
        # Handle potential UNIQUE constraint violation on file_path
        logger.error(f"Error creating recording (possible duplicate path '{data_to_insert[1]}'): {e}", exc_info=True)
        raise ValueError(f"Recording with path '{data_to_insert[1]}' might already exist.") from e
    except sqlite3.Error as e:
        logger.error(f"Error creating recording: {e}", exc_info=True)
        raise

def update_recording(conn: sqlite3.Connection, recording_id: int, **kwargs) -> None:
    """Update fields of a recording."""
    if not kwargs: return
    valid_fields = [FIELD_FILENAME, FIELD_FILE_PATH, FIELD_DATE_CREATED, FIELD_DURATION,
                    FIELD_RAW_TRANSCRIPT, FIELD_PROCESSED_TEXT,
                    FIELD_RAW_TRANSCRIPT_FORMATTED, FIELD_PROCESSED_TEXT_FORMATTED]
    update_fields = {}
    for key, value in kwargs.items():
        if key in valid_fields:
            update_fields[key] = value
        else:
            logger.warning(f"Invalid field '{key}' provided for update_recording.")

    if not update_fields:
         logger.warning(f"No valid fields provided to update recording {recording_id}.")
         return

    parameters = [f"{key} = ?" for key in update_fields]
    values = list(update_fields.values())
    values.append(recording_id)
    sql = f"UPDATE {TABLE_RECORDINGS} SET {', '.join(parameters)} WHERE {FIELD_ID} = ?"

    try:
        cursor = conn.cursor()
        cursor.execute(sql, values)
        conn.commit()
        logger.info(f"Updated recording ID {recording_id} with fields: {', '.join(update_fields.keys())}")
    except sqlite3.Error as e:
        logger.error(f"Error updating recording {recording_id}: {e}", exc_info=True)
        raise

def delete_recording(conn: sqlite3.Connection, recording_id: int) -> None:
    """Delete a recording by ID."""
    # Note: Foreign key constraints should handle deleting associated entries
    # in recording_folders if set up correctly in FolderManager's init_database.
    sql = f'DELETE FROM {TABLE_RECORDINGS} WHERE {FIELD_ID}=?'
    try:
        cursor = conn.cursor()
        cursor.execute(sql, (recording_id,))
        conn.commit()
        logger.info(f"Deleted recording ID {recording_id}")
    except sqlite3.Error as e:
        logger.error(f"Error deleting recording {recording_id}: {e}", exc_info=True)
        raise

# --- Utility Queries ---
def recording_exists(conn: sqlite3.Connection, file_path: str) -> bool:
    """Check if a recording with the given file path already exists."""
    try:
        cursor = conn.cursor()
        # Use the index for potentially faster check
        cursor.execute(f"SELECT 1 FROM {TABLE_RECORDINGS} WHERE {FIELD_FILE_PATH}=? LIMIT 1", (file_path,))
        return cursor.fetchone() is not None
    except sqlite3.Error as e:
        logger.error(f"Error checking if recording exists for path '{file_path}': {e}", exc_info=True)
        raise

def search_recordings(conn: sqlite3.Connection, search_term: str) -> List[Tuple]:
    """Search recordings by filename or transcript content (case-insensitive)."""
    search_pattern = f"%{search_term}%"
    sql = f"""
    SELECT * FROM {TABLE_RECORDINGS}
    WHERE {FIELD_FILENAME} LIKE ?
       OR {FIELD_RAW_TRANSCRIPT} LIKE ?
       OR {FIELD_PROCESSED_TEXT} LIKE ?
    ORDER BY {FIELD_DATE_CREATED} DESC"""
    
    try:
        cursor = conn.cursor()
        cursor.execute(sql, (search_pattern, search_pattern, search_pattern))
        return cursor.fetchall()
    except sqlite3.Error as e:
        logger.error(f"Error searching recordings: {e}", exc_info=True)
        raise