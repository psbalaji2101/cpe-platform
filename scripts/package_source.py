"""Create a portable source bundle without credentials, dependencies or runtime data."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

root = Path(__file__).resolve().parents[1]
output = root.parent / 'cpe-platform-source.zip'
excluded = {'.env', 'LOCAL_ACCESS.md', '.venv', 'node_modules', 'dist', '__pycache__',
            '.pytest_cache', '.git', 'test-results', 'playwright-report', 'data', '.DS_Store'}
with ZipFile(output, 'w', ZIP_DEFLATED) as archive:
    for path in sorted(root.rglob('*')):
        relative = path.relative_to(root)
        if path.is_file() and not path.is_symlink() and not any(p in excluded or p.startswith('.env.') for p in relative.parts):
            archive.write(path, Path(root.name) / relative)
with ZipFile(output) as archive:
    assert archive.testzip() is None
    assert not any(set(Path(name).parts) & excluded for name in archive.namelist())
print(f'Created {output.name}: {output.stat().st_size:,} bytes; private credentials excluded.')
