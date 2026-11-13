"""
PyInstaller spec for the pywebview UI only (web_main.py). Leaves out the Qt frontend and Qt WebEngine.

Build: pyinstaller .\\submissions_web.spec --noconfirm
"""
import sys
from pathlib import Path
sys.path.append(Path(__name__).parent.joinpath('src').absolute().__str__())
from submissions import __version__, __project__, project_path

# NOTE: The Qt frontend, its charts and Qt WebEngine (bundled Chromium). Nothing the web UI runs imports these.
QT_FRONTEND = [
    "frontend",
    "PyQt6.QtWebEngineCore", "PyQt6.QtWebEngineWidgets", "PyQt6.QtWebEngineQuick", "PyQt6.QtWebChannel",
    "PyQt6.QtQml", "PyQt6.QtQuick", "PyQt6.QtPdf", "PyQt6.QtPdfWidgets",
    "pyqtgraph", "kaleido",
]
# NOTE: Optional imports of pandas/numpy and friends that the app never uses.
UNUSED = ["tkinter", "matplotlib", "scipy", "IPython", "jupyter", "notebook", "pytest", "sphinx", "docutils",
        "pyarrow", "numba"]

name = f"{__project__}_web_{__version__}"

a = Analysis(
    ['src\\submissions\\web_main.py'],
    pathex=[project_path.absolute().__str__(), project_path.joinpath("src", "submissions").__str__()],
    binaries=[],
    datas=[
        ("src\\config.yml", "files"),
        ("src\\submissions\\templates", "files\\templates"),
        ("src\\submissions\\resources", "files\\resources"),
        ("src\\submissions\\webui\\static", "files\\webui\\static"),
        ("alembic.ini", "files"),
        ("src\\scripts\\*.py", "files\\scripts"),
    ],
    hiddenimports=["pyodbc", "webview.platforms.edgechromium", "webview.platforms.winforms", "clr",
                     "gql", "gql.transport.requests"],
    excludes=QT_FRONTEND + UNUSED,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data)
exe = EXE(
      pyz,
      a.scripts,
      [],
      exclude_binaries=True,
      name=name,
      debug=False,
      bootloader_ignore_signals=False,
      strip=False,
      upx=False,
      console=True,
      disable_windowed_traceback=False,
      argv_emulation=False,
      target_arch=None,
      codesign_identity=None,
      entitlements_file=None,
)
coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas, strip=False, upx=False, upx_exclude=[], name=name)

# NOTE: .NET (pythonnet/WebView2) refuses assemblies loaded from a network share unless the exe's config allows it.
Path(DISTPATH, name, f"{name}.exe.config").write_text(
    '<?xml version="1.0" encoding="utf-8"?>\n'
    '<configuration>\n'
    '  <runtime>\n'
    '    <loadFromRemoteSources enabled="true"/>\n'
    '  </runtime>\n'
    '</configuration>\n',
    encoding="utf-8",
)