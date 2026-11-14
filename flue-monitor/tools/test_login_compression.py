"""Compare the generated login gzip byte-for-byte with the C template."""
from pathlib import Path
import gzip
import re
import subprocess
import tempfile
root=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as directory:
    tmp=Path(directory);header=tmp/'assets.h'
    subprocess.run(['python3',str(root/'tools/generate_web_assets.py'),str(header)],check=True)
    source=(root/'main/rest_api.c').read_text().split('static const char login_page[] = ',1)[1].split('\n#endif',1)[0]
    (tmp/'login.c').write_text('#include <stdio.h>\n#include "assets.h"\nstatic const char login_page[] = '+source+'\nint main(void){fwrite(login_page,1,sizeof login_page-1,stdout);}\n')
    subprocess.run(['cc',str(tmp/'login.c'),'-o',str(tmp/'login')],check=True)
    expected=subprocess.check_output([str(tmp/'login')])
    h=header.read_text();array=re.search(r'asset_login_gzip\[\] = \{(.*?)\};',h,re.S).group(1)
    encoded=bytes(int(n) for n in re.findall(r'\d+',array))
    assert gzip.decompress(encoded)==expected
    assert b'?v=' in expected and b'cloudflare_token' not in expected
    print(f'PASS: identical login HTML, versioned font URLs; {len(expected)} bytes -> {len(encoded)} bytes gzip')
