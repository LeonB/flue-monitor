"""Check generated login bytes against the HTML asset and versioned font URLs."""
from pathlib import Path
import gzip
import re
import subprocess
import tempfile
import generate_web_assets as web
root=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as directory:
    header=Path(directory)/'assets.h'
    subprocess.run(['python3',str(root/'tools/generate_web_assets.py'),str(header)],check=True)
    expected=web.version_references((root/'main/web_ui/login.html').read_bytes())
    array=re.search(r'asset_login_gzip\[\] = \{(.*?)\};',header.read_text(),re.S).group(1)
    encoded=bytes(int(n) for n in re.findall(r'\d+',array))
    assert gzip.decompress(encoded)==expected
    assert b'?v=' in expected and b'cloudflare_token' not in expected
    print(f'PASS: identical login HTML, versioned font URLs; {len(expected)} bytes -> {len(encoded)} bytes gzip')
