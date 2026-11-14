#!/usr/bin/env python3
"""Check actual migrated functions with a host-built TF-PSA crypto library.

Pass --source (the SDK's tf-psa-crypto directory) and --library (the host
libtfpsacrypto.a). Expected values use Python's independent hashlib backend.
The normal auth regression separately covers failure handling and persistence.
"""
import argparse
import hashlib
from pathlib import Path
import subprocess
import tempfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source', type=Path, required=True)
parser.add_argument('--library', type=Path, required=True)
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
auth = (root / 'main/dashboard_auth.c').read_text()


def section(source, start, end):
    first = source.index(start)
    return source[first:source.index(end, first)]


salt = bytes(range(16))
expected_hash = hashlib.pbkdf2_hmac('sha256', b'compatibility-test', salt, 12000).hex()
source = '''
#include <psa/crypto.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <assert.h>
#define AUTH_PBKDF2_ROUNDS 12000
static void hex(const uint8_t *in,size_t n,char *out){
    static const char digits[]="0123456789abcdef";
    for(size_t i=0;i<n;i++){out[2*i]=digits[in[i]>>4];out[2*i+1]=digits[in[i]&15];}
    out[2*n]=0;
}
'''
source += section(auth, 'static bool derive(', 'static bool equal_secret(')
source += f'''
int main(void) {{
    assert(psa_crypto_init() == PSA_SUCCESS);
    uint8_t salt[16], output[32];
    char hash[65];
    for (int i = 0; i < 16; i++) salt[i] = i;
    assert(derive("compatibility-test", salt, output));
    hex(output, 32, hash);
    assert(!strcmp(hash, "{expected_hash}"));
    puts("PASS actual TF-PSA crypto: unchanged PBKDF2 credential hash");
}}
'''
with tempfile.TemporaryDirectory() as directory:
    source_path = Path(directory) / 'crypto-test.c'
    source_path.write_text(source)
    binary = Path(directory) / 'crypto-test'
    subprocess.run([
        'cc', '-I' + str(root / 'main'), '-I' + str(args.source / 'include'),
        '-I' + str(args.source / 'drivers/builtin/include'), str(source_path),
        str(args.library), '-o', str(binary),
    ], check=True)
    subprocess.run([str(binary)], check=True)
