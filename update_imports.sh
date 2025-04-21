#\!/bin/bash

# Files to update
files=(
  "app/MainTranscriptionWidget.py"
  "app/RecentRecordingsWidget.py"
  "app/ThemeManager.py"
  "app/SettingsDialog.py"
  "app/ui_utils.py"
  "app/FileDropWidget.py"
  "app/ControlPanelWidget.py"
  "app/RecordingListItem.py"
  "app/TextEditor.py"
  "app/VoiceRecorderWidget.py"
  "app/PromptManagerDialog.py"
  "app/FolderTreeWidget.py"
)

# Process each file
for file in "${files[@]}"; do
  echo "Processing $file..."
  
  # Read the file content
  content=$(cat "$file")
  
  # Replace the import statement (handles different import formats)
  updated_content=$(echo "$content" | sed -E 's/from app.utils import (.*resource_path)/from app.path_utils import resource_path\nfrom app.utils import \1/g' | sed -E 's/from app.utils import resource_path, /from app.path_utils import resource_path\nfrom app.utils import /g')
  
  # Remove duplicate import if it exists
  updated_content=$(echo "$updated_content" | sed -E 's/from app.utils import resource_path//g')
  
  # Write the updated content back to the file
  echo "$updated_content" > "$file"
done

echo "All imports updated\!"
