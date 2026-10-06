import PyInstaller.__main__
import os
import sys
import json
import site
from pathlib import Path
from importlib.metadata import version

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
if sys.platform == 'win32':
    windows_root = Path(os.environ['SystemRoot'])
    os.environ['PATH'] = os.pathsep.join(map(str, (
        Path(sys.executable).parent, Path(sys.base_prefix),
        windows_root / 'System32', windows_root,
    )))
sys.path.insert(0, str(ROOT))
for directory in ('build', 'dist'):
    if (ROOT / directory).resolve().parent != ROOT:
        raise RuntimeError(f'Build directory must stay inside {ROOT}: {directory}')
os.environ['PYINSTALLER_CONFIG_DIR'] = str(ROOT / 'build' / 'pyinstaller-cache')
if not site.ENABLE_USER_SITE and sys.prefix != sys.base_prefix:
    os.environ.setdefault('PYTHONUSERBASE', str(ROOT / 'build' / 'python-user'))
    site.USER_BASE = os.environ['PYTHONUSERBASE']
    site.USER_SITE = None

PyInstaller.__main__.run([
    str(ROOT / 'src' / 'main.py'),
    '--name=CIGA-Annotator',
    '--windowed',
    '--onefile',
    '--clean',
    '--noconfirm',
    f'--specpath={ROOT}',
    f'--workpath={ROOT / "build"}',
    f'--distpath={ROOT / "dist"}',
    f'--paths={ROOT}',
    f'--icon={ROOT / "assets" / "logo_black.png"}',
    f'--add-data={ROOT / "assets" / "logo_black.png"}{os.pathsep}.',
    f'--add-data={ROOT / "assets" / "logo_white.png"}{os.pathsep}.',
    # Qt's hooks collect the multimedia plugins and modules used by the app.
    '--collect-all=shiboken6',
])

exe_path = ROOT / 'dist' / 'CIGA-Annotator.exe'
if not exe_path.exists():
    raise FileNotFoundError(f'Expected PyInstaller output file not found: {exe_path}')
(ROOT / 'dist' / 'build-info.json').write_text(json.dumps({
    'application': 'CIGA-Annotator',
    'csv_schema': 'line,position,start_time,end_time,speakers,listeners,targets,custom columns',
    'python_version': sys.version.split()[0],
    'pyside6_version': version('PySide6'),
}, indent=2), encoding='utf-8')
print(f'Packaged executable: {exe_path}')
