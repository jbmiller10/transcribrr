# transcribrr.spec ─ reproducible freeze for Windows x64 Python 3.9
# run:  pyinstaller transcribrr.spec --noconfirm --clean
from PyInstaller.utils.hooks import collect_submodules, collect_data_files
block_cipher = None

hidden   = collect_submodules("torch")          # dynamic imports
datas    = collect_data_files(".",  # icons, json, config
           includes=["icons/**", "preset_prompts.json", "config.json"])

a = Analysis(
        ["main.py"],
        pathex=[],
        binaries=[],
        datas=datas,
        hiddenimports=hidden,
        noarchive=False,
        cipher=block_cipher,
)
pyz  = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe  = EXE(pyz, a.scripts,
        name="Transcribrr",
        icon="icons/app/app_icon.ico",
        console=False)
coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas,
        strip=False, upx=True, name="Transcribrr")
