import os
import json
import logging
import datetime
from app.DatabaseManager import DatabaseManager
from app.constants import DATABASE_PATH

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
        self.db_manager = DatabaseManager()
        
        # Set the correct database path from constants
        self.db_path = DATABASE_PATH
        
        # Create folders tables if they don't exist
        self.init_database()
        
        # Load existing folders
        self.load_folders()
    
    def init_database(self):
        """Initialize database tables for folders."""
        create_folders_table_query = '''
            CREATE TABLE IF NOT EXISTS folders (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                parent_id INTEGER,
                created_at TEXT NOT NULL,
                FOREIGN KEY (parent_id) REFERENCES folders (id)
                    ON DELETE CASCADE
            )
        '''
        
        create_recording_folders_table_query = '''
            CREATE TABLE IF NOT EXISTS recording_folders (
                recording_id INTEGER NOT NULL,
                folder_id INTEGER NOT NULL,
                PRIMARY KEY (recording_id, folder_id),
                FOREIGN KEY (recording_id) REFERENCES recordings (id)
                    ON DELETE CASCADE,
                FOREIGN KEY (folder_id) REFERENCES folders (id)
                    ON DELETE CASCADE
            )
        '''
        
        # Execute queries using DatabaseManager
        self.db_manager.execute_query(create_folders_table_query)
        self.db_manager.execute_query(create_recording_folders_table_query)
    
    def load_folders(self):
        """Load folders from database."""
        query = '''
            SELECT id, name, parent_id, created_at
            FROM folders
            ORDER BY name
        '''
        
        def on_folders_loaded(rows):
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
            logger.info(f"Loaded {len(self.folders)} folders")
        
        # Use the DatabaseManager to execute the query
        self.db_manager.execute_query(query, callback=on_folders_loaded)
    
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
        # Check for duplicate name at same level
        if self.folder_exists(name, parent_id):
            logger.warning(f"Folder with name '{name}' already exists at this level")
            if callback:
                callback(False, "A folder with this name already exists")
            return False
        
        created_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Query to insert the new folder
        query = '''
            INSERT INTO folders (name, parent_id, created_at)
            VALUES (?, ?, ?)
        '''
        params = (name, parent_id, created_at)
        
        def on_folder_created(result):
            if result and len(result) > 0:
                # Extract the folder ID from the result
                # This is typically the last inserted row ID
                folder_id = result[0][0] if isinstance(result[0], tuple) else result[0]
                
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
            else:
                # Handle the case where no ID was returned
                logger.error("Failed to get new folder ID")
                if callback:
                    callback(False, "Database error: Failed to get new folder ID")
                return False
        
        # First, insert the folder
        insert_query = query
        insert_params = params
        
        # Second, get the ID of the inserted folder
        get_id_query = "SELECT last_insert_rowid()"
        
        # Execute the insertion and then get the ID
        def after_insert(result):
            self.db_manager.execute_query(get_id_query, callback=on_folder_created)
        
        # Execute the insert query
        self.db_manager.execute_query(insert_query, insert_params, callback=after_insert)
        
        # The function returns immediately as the DB operation is async
        # The actual result handling is in the callback
        return True
    
    def rename_folder(self, folder_id, new_name, callback=None):
        """Rename an existing folder."""
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
        
        # Query to update the folder name
        query = '''
            UPDATE folders
            SET name = ?
            WHERE id = ?
        '''
        params = (new_name, folder_id)
        
        def on_folder_renamed(result):
            # Update in-memory structure regardless of result
            # (since we're using async, we won't have a result that indicates success/fail)
            for folder in self.folders:
                if folder['id'] == folder_id:
                    folder['name'] = new_name
                    break
            
            logger.info(f"Renamed folder ID {folder_id} to '{new_name}'")
            
            if callback:
                callback(True, None)
            
            return True
        
        # Execute the query
        self.db_manager.execute_query(query, params, callback=on_folder_renamed)
        
        # The function returns immediately as the DB operation is async
        return True
    
    def delete_folder(self, folder_id, callback=None):
        """Delete a folder and remove all recording associations."""
        # First, store the folder info for in-memory updates later
        folder_to_delete = self.get_folder_by_id(folder_id)
        if not folder_to_delete:
            logger.warning(f"Folder with ID {folder_id} not found for deletion")
            if callback:
                callback(False, "Folder not found")
            return False
        
        # Query to remove recording associations
        remove_associations_query = '''
            DELETE FROM recording_folders
            WHERE folder_id = ?
        '''
        
        # Query to delete the folder
        delete_folder_query = '''
            DELETE FROM folders
            WHERE id = ?
        '''
        
        def on_folder_deleted(result):
            # Update in-memory structure
            parent_folder = None
            
            # Find parent folder if it exists
            if folder_to_delete['parent_id'] is not None:
                for folder in self.folders:
                    if folder['id'] == folder_to_delete['parent_id']:
                        parent_folder = folder
                        break
            
            # Remove from parent's children if applicable
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
        
        # Function to execute folder deletion after associations are removed
        def after_associations_removed(result):
            # Now delete the folder itself
            self.db_manager.execute_query(delete_folder_query, (folder_id,), callback=on_folder_deleted)
        
        # First remove associations, then delete folder
        self.db_manager.execute_query(remove_associations_query, (folder_id,), callback=after_associations_removed)
        
        # The function returns immediately as the DB operation is async
        return True
    
    def add_recording_to_folder(self, recording_id, folder_id, callback=None):
        """Add a recording to a folder.
        
        This will remove the recording from any other folders it might be in,
        ensuring that a recording can only be in one folder at a time.
        """
        # First check if the association already exists
        check_query = '''
            SELECT 1 FROM recording_folders
            WHERE recording_id = ? AND folder_id = ?
        '''
        
        def on_association_added(result):
            logger.info(f"Added recording {recording_id} to folder {folder_id}")
            
            if callback:
                callback(True, None)
            
            return True
        
        def after_remove_from_other_folders(result):
            # Now add to the target folder
            insert_query = '''
                INSERT INTO recording_folders (recording_id, folder_id)
                VALUES (?, ?)
            '''
            self.db_manager.execute_query(insert_query, (recording_id, folder_id), callback=on_association_added)
        
        def on_check_completed(result):
            if result and len(result) > 0:
                # Association already exists
                logger.info(f"Recording {recording_id} is already in folder {folder_id}")
                if callback:
                    callback(True, None)
                return True
            
            # First remove this recording from all other folders
            remove_query = '''
                DELETE FROM recording_folders
                WHERE recording_id = ?
            '''
            
            # Remove from all existing folders, then add to the new one
            self.db_manager.execute_query(remove_query, (recording_id,), callback=after_remove_from_other_folders)
        
        # First check if the association exists
        self.db_manager.execute_query(check_query, (recording_id, folder_id), callback=on_check_completed)
        
        # The function returns immediately as the DB operations are async
        return True
    
    def remove_recording_from_folder(self, recording_id, folder_id, callback=None):
        """Remove a recording from a folder."""
        query = '''
            DELETE FROM recording_folders
            WHERE recording_id = ? AND folder_id = ?
        '''
        
        def on_association_removed(result):
            logger.info(f"Removed recording {recording_id} from folder {folder_id}")
            
            if callback:
                callback(True, None)
            
            return True
        
        # Execute the delete query
        self.db_manager.execute_query(query, (recording_id, folder_id), callback=on_association_removed)
        
        # The function returns immediately as the DB operation is async
        return True
    
    def get_recordings_in_folder(self, folder_id, callback=None):
        """Get all recordings in a folder."""
        query = '''
            SELECT r.id, r.filename, r.file_path, r.date_created, r.duration, 
                   r.raw_transcript, r.processed_text, r.raw_transcript_formatted, r.processed_text_formatted
            FROM recordings r
            JOIN recording_folders rf ON r.id = rf.recording_id
            WHERE rf.folder_id = ?
            ORDER BY r.date_created DESC
        '''
        
        def on_recordings_fetched(result):
            if callback:
                callback(True, result)
            
            return result
        
        # Execute the query
        self.db_manager.execute_query(query, (folder_id,), callback=on_recordings_fetched)
        
        # The function can't return the recordings directly as they're fetched asynchronously
        # The results will be passed to the callback function
        return []
    
    def get_folders_for_recording(self, recording_id, callback=None):
        """Get all folders containing a recording."""
        query = '''
            SELECT f.id, f.name, f.parent_id, f.created_at
            FROM folders f
            JOIN recording_folders rf ON f.id = rf.folder_id
            WHERE rf.recording_id = ?
            ORDER BY f.name
        '''
        
        def on_folders_fetched(result):
            if callback:
                callback(True, result)
            
            return result
        
        # Execute the query
        self.db_manager.execute_query(query, (recording_id,), callback=on_folders_fetched)
        
        # The function can't return the folders directly as they're fetched asynchronously
        # The results will be passed to the callback function
        return []
    
    def get_all_root_folders(self):
        """Get all root level folders (no parent)."""
        return [folder for folder in self.folders if folder['parent_id'] is None]
        
    def get_recordings_not_in_folders(self, callback=None):
        """Get all recordings that are not in any folder."""
        query = '''
            SELECT r.id, r.filename, r.file_path, r.date_created, r.duration, 
                   r.raw_transcript, r.processed_text, r.raw_transcript_formatted, r.processed_text_formatted
            FROM recordings r
            WHERE NOT EXISTS (
                SELECT 1 FROM recording_folders rf 
                WHERE rf.recording_id = r.id
            )
            ORDER BY r.date_created DESC
        '''
        
        def on_recordings_fetched(result):
            if callback:
                callback(True, result)
            
            return result
        
        # Execute the query
        self.db_manager.execute_query(query, callback=on_recordings_fetched)
        
        # The function can't return the recordings directly as they're fetched asynchronously
        # The results will be passed to the callback function
        return []
    
    def get_folder_by_id(self, folder_id):
        """Get a folder by ID."""
        for folder in self.folders:
            if folder['id'] == folder_id:
                return folder
        return None
    
    def get_folder_recording_count(self, folder_id, callback=None):
        """Get the number of recordings in a folder."""
        query = '''
            SELECT COUNT(*) FROM recording_folders
            WHERE folder_id = ?
        '''
        
        def on_count_fetched(result):
            # Extract the count from the result
            count = 0
            if result and len(result) > 0:
                count = result[0][0]
            
            if callback:
                callback(count)
            
            return count
        
        # Execute the query
        self.db_manager.execute_query(query, (folder_id,), callback=on_count_fetched)
        
        # For backward compatibility with code that expects an immediate result
        # This is a fallback and will only be correct if the folder has been previously loaded
        # and its count cached somewhere
        return 0
    
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
    
    def import_folder_structure(self, json_data, callback=None):
        """Import folder structure from JSON."""
        try:
            folders = json.loads(json_data)
            
            # Clear existing folder associations
            clear_associations_query = "DELETE FROM recording_folders"
            
            # Clear existing folders
            clear_folders_query = "DELETE FROM folders"
            
            # Function to process after clearing associations and folders
            def on_cleared(result):
                # Add all imported folders
                for folder in folders:
                    insert_query = '''
                        INSERT INTO folders (id, name, parent_id, created_at)
                        VALUES (?, ?, ?, ?)
                    '''
                    params = (folder['id'], folder['name'], folder['parent_id'], folder['created_at'])
                    self.db_manager.execute_query(insert_query, params)
                
                # Reload folders after a short delay to allow inserts to complete
                def reload_folders():
                    self.load_folders()
                    if callback:
                        callback(True, "Folder structure imported successfully")
                
                # Use QTimer to delay the reload
                from PyQt6.QtCore import QTimer
                QTimer.singleShot(500, reload_folders)
            
            # Execute clear folders after associations are cleared
            def on_associations_cleared(result):
                self.db_manager.execute_query(clear_folders_query, callback=on_cleared)
            
            # First clear associations
            self.db_manager.execute_query(clear_associations_query, callback=on_associations_cleared)
            
            return True
            
        except Exception as e:
            logger.error(f"Error importing folder structure: {e}")
            if callback:
                callback(False, str(e))
            return False