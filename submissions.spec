# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

#### custom for automation of documentation building ####
import sys, subprocess
from pathlib import Path
sys.path.append(Path(".").parent.joinpath('src').absolute().__str__())
from submissions import __version__, __project__, bcolors, project_path

doc_path = project_path.joinpath("docs").absolute()
build_path = project_path.joinpath(".venv", "Scripts", "sphinx-build").absolute().__str__()
print(bcolors.BOLD + "Running Sphinx subprocess to generate rst files..." + bcolors.ENDC)
api_path = project_path.joinpath(".venv", "Scripts", "sphinx-apidoc").absolute().__str__()
subprocess.run([api_path, "-o", doc_path.joinpath("source").__str__(), project_path.joinpath("src", "submissions").__str__(), "-f"])
print(bcolors.BOLD + "Running Sphinx subprocess to generate html docs..." + bcolors.ENDC)
subprocess.run([build_path, doc_path.joinpath("source").__str__(), doc_path.joinpath("build").__str__(), "-a"])
#########################################################

a = Analysis(
    ['src\\submissions\\__main__.py'],
    pathex=[project_path.absolute().__str__()],
    binaries=[],
    datas=[
            ("src\\config.yml", "files"),
            ("src\\submissions\\templates\\*", "files\\templates"),
            ("src\\submissions\\templates\\css\\*", "files\\templates\\css"),
            ("docs\\build", "files\\docs"),
            ("src\\submissions\\resources\\*", "files\\resources"),
            ("alembic.ini", "files"),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["*.xlsx"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=f"{__project__}_{__version__}",
    debug=True,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    # Change these for non-beta versions
    #console=False,
    #disable_windowed_traceback=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name=f"{__project__}_{__version__}",
)
