#!/usr/bin/env python3
"""Measure lossless PNG compression; --write applies only smaller embedded assets.

Optional maintenance dependencies: Pillow and zopfli. Normal firmware builds
consume the resulting PNG files and do not need either package.
"""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path

from PIL import Image
import zopfli.png

ROOT = Path(__file__).resolve().parents[1]
COLOR_CHUNKS = ('gAMA', 'cHRM', 'sRGB', 'iCCP', 'pHYs')


def chunks(data):
    result = {}
    offset = 8
    while offset < len(data):
        size = int.from_bytes(data[offset:offset+4], 'big')
        name = data[offset+4:offset+8].decode('ascii')
        result.setdefault(name, []).append(data[offset+8:offset+8+size])
        offset += size + 12
    return result


def equivalent(original, candidate):
    with Image.open(io.BytesIO(original)) as before, Image.open(io.BytesIO(candidate)) as after:
        if (before.size != after.size or before.n_frames != 1 or after.n_frames != 1 or
                before.convert('RGBA').tobytes() != after.convert('RGBA').tobytes()):
            raise ValueError('PNG pixels or dimensions changed')
    before, after = chunks(original), chunks(candidate)
    if any(before.get(key) != after.get(key) for key in COLOR_CHUNKS):
        raise ValueError('PNG color or pixel-density metadata changed')


def embedded_size(data):
    return len(gzip.compress(data, compresslevel=9, mtime=0))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args()
    archive = ROOT / '.cache/asset-optimization'
    records = []
    for path in sorted((ROOT / 'main/web_ui').glob('*.png')):
        original = path.read_bytes()
        candidates = [original]
        for use_zopfli in (False, True):
            candidate = zopfli.png.optimize(original, use_zopfli=use_zopfli,
                                           filter_strategies='01234', num_iterations=5,
                                           num_iterations_large=5, keepchunks=COLOR_CHUNKS,
                                           lossy_transparent=False, lossy_8bit=False)
            equivalent(original, candidate)
            candidates.append(candidate)
        best = min(candidates, key=embedded_size)
        before, after = embedded_size(original), embedded_size(best)
        if args.write and after < before:
            archive.mkdir(parents=True, exist_ok=True)
            backup = archive / (path.stem + '-' + hashlib.sha256(original).hexdigest()[:16] + '.png')
            if not backup.exists():
                backup.write_bytes(original)
            path.write_bytes(best)
        record = {'file': path.name, 'before': before, 'after': after, 'saved': before-after}
        records.append(record)
        print(json.dumps(record), flush=True)
    report = {'applied': args.write, 'saved_bytes': sum(r['saved'] for r in records), 'assets': records}
    archive.mkdir(parents=True, exist_ok=True)
    (archive / 'png-report.json').write_text(json.dumps(report, indent=2) + '\n')
    print('Embedded bytes saved:', report['saved_bytes'])


if __name__ == '__main__':
    main()
