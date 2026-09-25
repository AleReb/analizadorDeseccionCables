"""Build the static Pages artifact, sharing the original Python detector."""
from pathlib import Path
import shutil

root = Path(__file__).resolve().parent
target = root / 'build' / 'web'
target.mkdir(parents=True, exist_ok=True)
for source in (root / 'web').iterdir():
    if source.is_file():
        shutil.copy2(source, target / source.name)
for name in ('automatic_measurement.py', 'LICENSE'):
    shutil.copy2(root / name, target / name)
(target / '.nojekyll').touch()
print(f'Web generated: {target}')
