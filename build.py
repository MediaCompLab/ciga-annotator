import PyInstaller.__main__
import shutil
import os

# Clean previous builds to avoid cache poisoning
if os.path.exists('build'): shutil.rmtree('build')
if os.path.exists('dist'): shutil.rmtree('dist')
if os.path.exists('CIGA-Annotator.spec'): os.remove('CIGA-Annotator.spec')

PyInstaller.__main__.run([
    'src/main.py',
    '--name=CIGA-Annotator',
    '--windowed',
    '--onefile',
    '--clean',
    '--icon=assets/logo_black.png',
    f'--add-data=assets/logo_black.png{os.pathsep}.',
    f'--add-data=assets/logo_white.png{os.pathsep}.',
    '--collect-all=PySide6',
    '--collect-all=shiboken6',
])
