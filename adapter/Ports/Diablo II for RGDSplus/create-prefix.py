#!/usr/bin/env python3
"""Initialize Wine's filesystem without firmware formatting utilities."""
import gzip
from pathlib import Path
import shutil
import sys


def create_prefix(port):
    image = port / 'prefix.ext4'
    if image.is_file():
        return
    temporary = port / 'prefix.ext4.new'
    # Exclusive creation leaves any earlier incomplete image untouched.
    with temporary.open('xb') as dest:
        try:
            with gzip.open(port / 'prefix-empty.ext4.gz', 'rb') as source:
                shutil.copyfileobj(source, dest)
            if dest.tell() != 512 * 1024 * 1024:
                raise ValueError('Invalid empty prefix image size')
        except BaseException:
            temporary.unlink()
            raise
    temporary.replace(image)


if __name__ == '__main__':
    try:
        create_prefix(Path(sys.argv[1]))
    except Exception as error:
        sys.exit(f'Cannot create Wine prefix: {error}')
