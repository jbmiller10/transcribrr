import os
import json
import logging
import sqlite3
from app.utils import resource_path

logger = logging.getLogger('transcribrr')

class FolderManager:
    """Manages user-created folder structure for organizing recordings."""
    
    # Singleton instance
    _instance = None
    
    @classmethod
    def instance(cls):
        """Get the singleton instance of FolderManager."""
        if cls._instance is None:
            cls._instance = FolderManager()
        return cls._instance
    
    def __init__(self):
        """Initialize the folder manager."""
        self.folders = []
        self.db_path = resource_path("./database/database.sqlite")
        
        # Create folders table if it doesn't exist
        self.init_database()
        
        # Load existing folders
        self.load_folders()
    
    def init_database(self):
        """Initialize database tables for folders."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Create folders table if it doesn't exist
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS folders (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    parent_id INTEGER,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (parent_id) REFERENCES folders (id)
                        ON DELETE CASCADE
                )
            ''')
            
            # Create recording_folders table to relate recordings to folders
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS recording_folders (
                    recording_id INTEGER NOT NULL,
                    folder_id INTEGER NOT NULL,
                    PRIMARY KEY (recording_id, folder_id),
                    FOREIGN KEY (recording_id) REFERENCES recordings (id)
                        ON DELETE CASCADE,
                    FOREIGN KEY (folder_id) REFERENCES folders (id)
                        ON DELETE CASCADE
                )
            ''')
            
            conn.commit()
        except Exception as e:
            logger.error(f"Error initializing folder database: {e}")
        finally:
            if conn:
                conn.close()
    
    def load_folders(self):
        """Load folders from database."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT id, name, parent_id, created_at
                FROM folders
                ORDER BY name
            ''')
            
            rows = cursor.fetchall()
            self.folders = []
            
            for row in rows:
                folder = {
                    'id': row[0],
                    'name': row[1],
                    'parent_id': row[2],
                    'created_at': row[3],
                    'children': []
                }
                self.folders.append(folder)
            
            # Process relationships
            self.build_folder_structure()
            
        except Exception as e:
            logger.error(f"Error loading folders: {e}")
        finally:
            if conn:
                conn.close()
    
    def build_folder_structure(self):
        """Build hierarchical folder structure from flat list."""
        # Create a temporary dictionary for quick lookup
        folder_dict = {folder['id']: folder for folder in self.folders}
        
        # Process relationships
        for folder in self.folders:
            if folder['parent_id'] is not None:
                parent_folder = folder_dict.get(folder['parent_id'])
                if parent_folder:
                    parent_folder['children'].append(folder)
    
    def create_folder(self, name, parent_id=None, callback=None):
        """Create a new folder in the database."""
        try:
            import datetime
            
            # Check for duplicate name at same level
            if self.folder_exists(name, parent_id):
                logger.warning(f"Folder with name '{name}' already exists at this level")
                if callback:
                    callback(False, "A folder with this name already exists")
                return False
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            created_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            cursor.execute('''
                INSERT INTO folders (name, parent_id, created_at)
                VALUES (?, ?, ?)
            ''', (name, parent_id, created_at))
            
            folder_id = cursor.lastrowid
            conn.commit()
            
            # Add to in-memory structure
            new_folder = {
                'id': folder_id,
                'name': name,
                'parent_id': parent_id,
                'created_at': created_at,
                'children': []
            }
            
            self.folders.append(new_folder)
            
            # Update parent folder's children if applicable
            if parent_id is not None:
                for folder in self.folders:
                    if folder['id'] == parent_id:
                        folder['children'].append(new_folder)
                        break
            
            logger.info(f"Created folder: {name} (ID: {folder_id})")
            
            if callback:
                callback(True, folder_id)
            
            return True
            
        except Exception as e:
            logger.error(f"Error creating folder: {e}")
            if callback:
                callback(False, str(e))
            return False
        finally:
            if conn:
                conn.close()
    
    def rename_folder(self, folder_id, new_name, callback=None):
        """Rename an existing folder."""
        try:
            # Check for duplicate name at same level
            folder = self.get_folder_by_id(folder_id)
            if not folder:
                logger.warning(f"Folder with ID {folder_id} not found")
                if callback:
                    callback(False, "Folder not found")
                return False
                
            if self.folder_exists(new_name, folder['parent_id'], exclude_id=folder_id):
                logger.warning(f"Folder with name '{new_name}' already exists at this level")
                if callback:
                    callback(False, "A folder with this name already exists")
                return False
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE folders
                SET name = ?
                WHERE id = ?
            ''', (new_name, folder_id))
            
            conn.commit()
            
            # Update in-memory structure
            for folder in self.folders:
                if folder['id'] == folder_id:
                    folder['name'] = new_name
                    break
            
            logger.info(f"Renamed folder ID {folder_id} to '{new_name}'")
            
            if callback:
                callback(True, None)
            
            return True
            
        except Exception as e:
            logger.error(f"Error renaming folder: {e}")
            if callback:
                callback(False, str(e))
            return False
        finally:
            if conn:
                conn.close()
    
    def delete_folder(self, folder_id, callback=None):
        """Delete a folder and remove all recording associations."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # First remove recording associations
            cursor.execute('''
                DELETE FROM recording_folders
                WHERE folder_id = ?
            ''', (folder_id,))
            
            # Then delete the folder
            cursor.execute('''
                DELETE FROM folders
                WHERE id = ?
            ''', (folder_id,))
            
            conn.commit()
            
            # Update in-memory structure
            folder_to_delete = None
            parent_folder = None
            
            for folder in self.folders:
                if folder['id'] == folder_id:
                    folder_to_delete = folder
                    break
            
            if folder_to_delete:
                # Remove from parent's children
                if folder_to_delete['parent_id'] is not None:
                    for folder in self.folders:
                        if folder['id'] == folder_to_delete['parent_id']:
                            parent_folder = folder
                            break
                    
                    if parent_folder:
                        parent_folder['children'] = [
                            child for child in parent_folder['children'] 
                            if child['id'] != folder_id
                        ]
                
                # Remove from list
                self.folders = [folder for folder in self.folders if folder['id'] != folder_id]
            
            logger.info(f"Deleted folder ID {folder_id}")
            
            if callback:
                callback(True, None)
            
            return True
            
        except Exception as e:
            logger.error(f"Error deleting folder: {e}")
            if callback:
                callback(False, str(e))
            return False
        finally:
            if conn:
                conn.close()
    
    def add_recording_to_folder(self, recording_id, folder_id, callback=None):
        """Add a recording to a folder."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Check if the association already exists
            cursor.execute('''
                SELECT 1 FROM recording_folders
                WHERE recording_id = ? AND folder_id = ?
            ''', (recording_id, folder_id))
            
            if cursor.fetchone():
                logger.info(f"Recording {recording_id} is already in folder {folder_id}")
                if callback:
                    callback(True, None)
                return True
            
            # Add the association
            cursor.execute('''
                INSERT INTO recording_folders (recording_id, folder_id)
                VALUES (?, ?)
            ''', (recording_id, folder_id))
            
            conn.commit()
            
            logger.info(f"Added recording {recording_id} to folder {folder_id}")
            
            if callback:
                callback(True, None)
            
            return True
            
        except Exception as e:
            logger.error(f"Error adding recording to folder: {e}")
            if callback:
                callback(False, str(e))
            return False
        finally:
            if conn:
                conn.close()
    
    def remove_recording_from_folder(self, recording_id, folder_id, callback=None):
        """Remove a recording from a folder."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                DELETE FROM recording_folders
                WHERE recording_id = ? AND folder_id = ?
            ''', (recording_id, folder_id))
            
            conn.commit()
            
            logger.info(f"Removed recording {recording_id} from folder {folder_id}")
            
            if callback:
                callback(True, None)
            
            return True
            
        except Exception as e:
            logger.error(f"Error removing recording from folder: {e}")
            if callback:
                callback(False, str(e))
            return False
        finally:
            if conn:
                conn.close()
    
    def get_recordings_in_folder(self, folder_id, callback=None):
        """Get all recordings in a folder."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT r.id, r.filename, r.file_path, r.date_created, r.duration, 
                       r.raw_transcript, r.processed_text, r.raw_transcript_formatted, r.processed_text_formatted
                FROM recordings r
                JOIN recording_folders rf ON r.id = rf.recording_id
                WHERE rf.folder_id = ?
                ORDER BY r.date_created DESC
            ''', (folder_id,))
            
            recordings = cursor.fetchall()
            
            if callback:
                callback(True, recordings)
            
            return recordings
            
        except Exception as e:
            logger.error(f"Error getting recordings in folder: {e}")
            if callback:
                callback(False, str(e))
            return []
        finally:
            if conn:
                conn.close()
    
    def get_folders_for_recording(self, recording_id, callback=None):
        """Get all folders containing a recording."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT f.id, f.name, f.parent_id, f.created_at
                FROM folders f
                JOIN recording_folders rf ON f.id = rf.folder_id
                WHERE rf.recording_id = ?
                ORDER BY f.name
            ''', (recording_id,))
            
            folders = cursor.fetchall()
            
            if callback:
                callback(True, folders)
            
            return folders
            
        except Exception as e:
            logger.error(f"Error getting folders for recording: {e}")
            if callback:
                callback(False, str(e))
            return []
        finally:
            if conn:
                conn.close()
    
    def get_all_root_folders(self):
        """Get all root level folders (no parent)."""
        return [folder for folder in self.folders if folder['parent_id'] is None]
    
    def get_folder_by_id(self, folder_id):
        """Get a folder by ID."""
        for folder in self.folders:
            if folder['id'] == folder_id:
                return folder
        return None
    
    def get_folder_recording_count(self, folder_id):
        """Get the number of recordings in a folder."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT COUNT(*) FROM recording_folders
                WHERE folder_id = ?
            ''', (folder_id,))
            
            count = cursor.fetchone()[0]
            return count
            
        except Exception as e:
            logger.error(f"Error getting recording count for folder {folder_id}: {e}")
            return 0
        finally:
            if conn:
                conn.close()
    
    def folder_exists(self, name, parent_id=None, exclude_id=None):
        """Check if a folder with the given name exists at the specified level."""
        for folder in self.folders:
            if folder['name'] == name and folder['parent_id'] == parent_id:
                if exclude_id and folder['id'] == exclude_id:
                    continue
                return True
        return False
    
    def export_folder_structure(self):
        """Export folder structure as JSON for backup."""
        return json.dumps(self.folders, indent=2)
    
    def import_folder_structure(self, json_data):
        """Import folder structure from JSON."""
        try:
            folders = json.loads(json_data)
            
            # Clear existing folders
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("DELETE FROM recording_folders")
            cursor.execute("DELETE FROM folders")
            
            # Add imported folders
            for folder in folders:
                cursor.execute('''
                    INSERT INTO folders (id, name, parent_id, created_at)
                    VALUES (?, ?, ?, ?)
                ''', (folder['id'], folder['name'], folder['parent_id'], folder['created_at']))
            
            conn.commit()
            
            # Reload folders
            self.load_folders()
            
            return True
        except Exception as e:
            logger.error(f"Error importing folder structure: {e}")
            return False
        finally:
            if conn:
                conn.close()