# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Build on the target OS: python build_release.py."""
import ast
import importlib.metadata
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NAME = 'AnalizadorCables'


def main():
    if sys.platform not in ('win32', 'darwin'):
        raise SystemExit('Build on Windows or macOS; cross-compilation is not supported.')
    tree = ast.parse((ROOT / 'measure_wire_cross_section_v5_1.py').read_text(encoding='utf-8'))
    version = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                   and any(isinstance(t, ast.Name) and t.id == '__version__' for t in n.targets))
    target = 'windows' if sys.platform == 'win32' else 'macos'
    architecture = platform.machine().lower()
    release_name = f'{NAME}-{version}-{target}-{architecture}'
    release = ROOT / 'dist' / release_name
    if release.exists():
        raise SystemExit(f'Release already exists: {release}. Move it before rebuilding.')
    subprocess.run([
        sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--windowed',
        '--onefile' if sys.platform == 'win32' else '--onedir',
        '--name', NAME, '--distpath', str(ROOT / 'build' / 'bundles'),
        '--workpath', str(ROOT / 'build' / 'pyinstaller'),
        '--specpath', str(ROOT / 'build'), '--hidden-import', 'automatic_measurement',
        '--osx-bundle-identifier', 'org.analizadorcables.desktop',
        str(ROOT / 'launcher.py'),
    ], cwd=ROOT, check=True)
    release.mkdir(parents=True)
    artifact = NAME + ('.exe' if sys.platform == 'win32' else '.app')
    source = ROOT / 'build' / 'bundles' / artifact
    if source.is_dir():
        shutil.copytree(source, release / artifact, symlinks=True)
    else:
        shutil.copy2(source, release / artifact)
    for name in ('LICENSE', 'README.md', 'CHANGELOG.md', 'REFERENTE.jpeg'):
        shutil.copy2(ROOT / name, release / name)
    # Ship corresponding source and dependency notices alongside the binary.
    sources = release / 'source'
    sources.mkdir()
    for pattern in ('*.py', 'requirements*.txt', '.gitignore', '.gitattributes'):
        for path in ROOT.glob(pattern):
            shutil.copy2(path, sources / path.name)
    shutil.copytree(ROOT / '.github', sources / '.github')
    licenses = release / 'third-party-licenses'
    licenses.mkdir()
    for distribution in importlib.metadata.distributions():
        for file in distribution.files or ():
            if any(word in str(file).lower() for word in ('license', 'copying', 'copyright')):
                path = distribution.locate_file(file)
                if path.is_file() and path.suffix.lower() not in ('.py', '.pyc', '.pyd'):
                    destination = licenses / distribution.metadata['Name'] / str(file).replace('..', '_')
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(path, destination)
    runtime_license = Path(sys.base_prefix) / 'LICENSE.txt'
    if runtime_license.exists():
        shutil.copy2(runtime_license, licenses / 'Python-LICENSE.txt')
    executable = release / artifact
    if sys.platform == 'darwin':
        executable = executable / 'Contents' / 'MacOS' / NAME
    smoke = ROOT / 'build' / f'smoke-{target}.json'
    if smoke.exists():
        smoke.unlink()
    subprocess.run([str(executable), '--smoke-test', str(smoke)], check=True, timeout=120)
    if not smoke.exists() or '"status": "ok"' not in smoke.read_text(encoding='utf-8'):
        raise RuntimeError('Packaged smoke test did not report success')
    archive = ROOT / 'dist' / f'{release_name}.zip'
    if sys.platform == 'darwin':
        subprocess.run(['ditto', '-c', '-k', '--sequesterRsrc', '--keepParent',
                        str(release), str(archive)], check=True)
    else:
        shutil.make_archive(str(archive.with_suffix('')), 'zip', release.parent, release.name)
    print(f'Packaged and smoke-tested: {archive}')


if __name__ == '__main__':
    main()
