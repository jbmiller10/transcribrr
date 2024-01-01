import sqlite3
from sqlite3 import Error
import os
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
def create_recording(conn, recording):
    """
    Create a new recording into the recordings table
    :param conn:
    :param recording: (filename, file_path, date_created, duration, raw_transcript, processed_text)
    :return: recording id
    """
    sql = ''' INSERT INTO recordings(filename, file_path, date_created, duration, raw_transcript, processed_text)
              VALUES(?,?,?,?,?,?) '''
    cur = conn.cursor()
    cur.execute(sql, recording)
    conn.commit()
    return cur.lastrowid

def get_all_recordings(conn):
    """
    Query all rows in the recordings table
    :param conn: the Connection object
    :return:
    """
    cur = conn.cursor()
    cur.execute("SELECT * FROM recordings")

    rows = cur.fetchall()

    return rows
def get_recording_by_id(conn, id):
    """Get a single recording by its ID."""
    cur = conn.cursor()
    cur.execute("SELECT * FROM recordings WHERE id=?", (id,))
    row = cur.fetchone()
    return row

def update_recording(conn, recording_id, **kwargs):
    """
    Update fields of a recording given by recording_id with values in kwargs
    :param conn: Database connection object
    :param recording_id: ID of the recording to update
    :param kwargs: Dictionary of column names and their new values
    :return: None
    """
    parameters = [f"{key} = ?" for key in kwargs]
    values = list(kwargs.values())
    values.append(recording_id)
    sql = f"UPDATE recordings SET {', '.join(parameters)} WHERE id = ?"
    cur = conn.cursor()
    cur.execute(sql, values)
    conn.commit()

def delete_recording(conn, id):
    """
    Delete a recording by recording id
    :param conn:  Connection to the SQLite database
    :param id: id of the recording
    :return:
    """
    sql = 'DELETE FROM recordings WHERE id=?'
    cur = conn.cursor()
    cur.execute(sql, (id,))
    conn.commit()

def create_db():
    database = "./database/database.sqlite"
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
                                            processed_text TEXT
                                         ); """

        # Create a database connection and create tables
        conn = create_connection(database)
        if conn is not None:
            create_table(conn, sql_create_recordings_table)
        else:
            print("Errr.")

if __name__ == '__main__':
    create_db()