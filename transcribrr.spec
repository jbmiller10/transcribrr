# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('icons', 'icons'), ('config.json', '.'), ('database', 'database'), ('logs', 'logs'), ('Recordings', 'Recordings')],
    hiddenimports=['PyQt6', 'PyQt6.QtCore', 'PyQt6.QtGui', 'PyQt6.QtWidgets', 'PyQt6.QtPrintSupport', 'PyQt6.QtSvg', 'torch', 'torchaudio', 'transformers', 'numpy', 'pyaudio', 'pydub', 'moviepy', 'moviepy.editor', 'yt_dlp', 'openai', 'keyring', 'requests', 'PyPDF2', 'docx', 'htmldocx', 'weasyprint', 'app', 'app.MainWindow', 'app.MainTranscriptionWidget', 'app.TextEditor', 'app.utils', 'app.ui_utils', 'app.ThemeManager', 'app.ResponsiveUI', 'app.services.transcription_service', 'app.threads.TranscriptionThread', 'app.threads.GPT4ProcessingThread', 'app.threads.TranscodingThread', 'app.threads.YouTubeDownloadThread', 'app.SettingsDialog', 'app.PromptManagerDialog', 'app.ToggleSwitch', 'app.ControlPanelWidget', 'app.VoiceRecorderWidget', 'app.SVGToggleButton', 'app.FileDropWidget', 'app.RecentRecordingsWidget', 'app.RecordingListItem', 'app.FolderManager', 'app.FolderTreeWidget', 'app.DatabaseManager'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Transcribrr',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['icons/app/app_icon.icns'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Transcribrr',
)
app = BUNDLE(
    coll,
    name='Transcribrr.app',
    icon='icons/app/app_icon.icns',
    bundle_identifier=None,
)
