import sqlite3
from sqlite3 import Error
import os
import json
from app.utils import resource_path

def create_connection(db_file):
    conn = None
    try:
        conn = sqlite3.connect(db_file)
        return conn
    except Error as e:
        print(e)

    return conn

def create_table(conn, create_table_sql):
    try:
        c = conn.cursor()
        c.execute(create_table_sql)
    except Error as e:
        print(e)

def create_config_file():
    config = {
        "transcription_quality": "openai/whisper-large-v3",
        "gpt_model": "gpt-4o",
        "max_tokens": 16000,
        "temperature": 1.0,
        "speaker_detection_enabled": False,
        "transcription_language": "english"
    }
    with open(resource_path('config.json'), 'w') as config_file:
        json.dump(config, config_file, indent=4)

def create_recording(conn, recording):
    """Insert recording into table, return ID."""
    sql = ''' INSERT INTO recordings(filename, file_path, date_created, duration, raw_transcript, processed_text)
              VALUES(?,?,?,?,?,?) '''
    cur = conn.cursor()
    cur.execute(sql, recording)
    conn.commit()
    return cur.lastrowid

def get_all_recordings(conn):
    """Return all recordings."""
    cur = conn.cursor()
    cur.execute("SELECT * FROM recordings")

    rows = cur.fetchall()

    return rows

def get_recording_by_id(conn, id):
    """Return recording by ID."""
    cur = conn.cursor()
    cur.execute("SELECT * FROM recordings WHERE id=?", (id,))
    row = cur.fetchone()
    return row

def update_recording(conn, recording_id, **kwargs):
    """Update recording fields."""
    if not kwargs:
        return  # Nothing to update
    parameters = [f"{key} = ?" for key in kwargs]
    values = list(kwargs.values())
    values.append(recording_id)
    sql = f"UPDATE recordings SET {', '.join(parameters)} WHERE id = ?"
    cur = conn.cursor()
    cur.execute(sql, values)
    conn.commit()

def delete_recording(conn, id):
    """Delete recording by ID."""
    sql = 'DELETE FROM recordings WHERE id=?'
    cur = conn.cursor()
    cur.execute(sql, (id,))
    conn.commit()

def create_db():
    database = resource_path("./database/database.sqlite")
    config_path = resource_path('config.json')
    if not os.path.exists(resource_path('./database')):
        os.makedirs(resource_path('./database'))
    if os.path.exists(database):
        pass
    else:
        sql_create_recordings_table = """ CREATE TABLE IF NOT EXISTS recordings (
                                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                                            filename TEXT NOT NULL,
                                            file_path TEXT NOT NULL,
                                            date_created TEXT NOT NULL,
                                            duration TEXT NOT NULL,
                                            raw_transcript TEXT,
                                            processed_text TEXT,
                                            raw_transcript_formatted BLOB, 
                                            processed_text_formatted BLOB
                                         ); """

        # Create a database connection and create tables
        conn = create_connection(database)
        if conn is not None:
            create_table(conn, sql_create_recordings_table)
            conn.close()
        else:
            print("Error! Cannot create the database connection.")

    # Create config file if it doesn't exist
    if not os.path.exists(config_path):
        create_config_file()