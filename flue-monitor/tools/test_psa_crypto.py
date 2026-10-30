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
pagekite = (root / 'main/pagekite_tunnel.c').read_text()


def section(source, start, end):
    first = source.index(start)
    return source[first:source.index(end, first)]


salt = bytes(range(16))
expected_hash = hashlib.pbkdf2_hmac('sha256', b'compatibility-test', salt, 12000).hex()
expected_signature = '00010203' + hashlib.sha1(b'test-secrettest-payload00010203').hexdigest()[:28]
expected_ddns = '00010203' + hashlib.sha1(b'test-secrettest.example:192.0.2.1' + b'00010203').hexdigest()
source = '''
#include <psa/crypto.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <assert.h>
#define AUTH_PBKDF2_ROUNDS 12000
#define SETTINGS_PAGEKITE_TEXT_MAX_LEN 128
static const char *secret = "test-secret", *domain = "test.example";
static void die(const char *message) {
    fprintf(stderr, "%s", message);
    exit(1);
}
static void esp_fill_random(void *buffer, size_t length) {
    for (size_t i = 0; i < length; i++) ((unsigned char *)buffer)[i] = i;
}
'''
source += section(auth, 'static bool derive(', 'static bool equal_secret(')
source += section(pagekite, 'static void hex(', 'static void chunk(')
source += section(pagekite, 'static void ddns_signature(', 'typedef struct { char body')
source += f'''
int main(void) {{
    assert(psa_crypto_init() == PSA_SUCCESS);
    uint8_t salt[16], output[32];
    char hash[65], signature_out[37], dns[49];
    for (int i = 0; i < 16; i++) salt[i] = i;
    assert(derive("compatibility-test", salt, output));
    hex(output, 32, hash);
    assert(!strcmp(hash, "{expected_hash}"));
    signature("test-payload", signature_out);
    assert(!strcmp(signature_out, "{expected_signature}"));
    ddns_signature("192.0.2.1", dns);
    assert(!strcmp(dns, "{expected_ddns}"));
    puts("PASS actual TF-PSA crypto: unchanged PBKDF2 credential hash, relay and DDNS signatures");
}}
'''
with tempfile.TemporaryDirectory() as directory:
    source_path = Path(directory) / 'crypto-test.c'
    source_path.write_text(source)
    binary = Path(directory) / 'crypto-test'
    subprocess.run([
        'cc', '-I' + str(args.source / 'include'),
        '-I' + str(args.source / 'drivers/builtin/include'), str(source_path),
        str(args.library), '-o', str(binary),
    ], check=True)
    subprocess.run([str(binary)], check=True)
