#!/usr/bin/env python3
"""Look inside a built .cngm next-word model.

Usage: python3 tools/inspect-cngm.py mn [word ...]
"""
import pathlib
import struct
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
LEXICONS = ROOT / "Lexicons"


def load(code):
    """Return {word: [(follower, probability), ...]} and the word list."""
    data = (LEXICONS / f"{code}.cngm").read_bytes()
    count = struct.unpack_from("<I", data, 8)[0]
    previous = [struct.unpack_from("<I", data, 12 + 4 * i)[0] for i in range(count)]
    following = [struct.unpack_from("<I", data, 12 + 4 * count + 4 * i)[0] for i in range(count)]
    probability = [data[12 + 8 * count + i] for i in range(count)]
    clex = (LEXICONS / f"{code}.clex").read_bytes()
    words = struct.unpack_from("<I", clex, 8)[0]
    size = struct.unpack_from("<I", clex, 12)[0]
    # header, alphabet table, letter matrix, offsets, probabilities, lengths
    offsets_at = 16 + 4 * size + (size + 1) * size
    words_at = offsets_at + 4 * (words + 1) + 2 * words
    offsets = [struct.unpack_from("<I", clex, offsets_at + 4 * i)[0] for i in range(words + 1)]
    names = []
    for i in range(words):
        raw = clex[words_at + offsets[i]:words_at + offsets[i + 1]]
        names.append(raw.decode("utf-8"))
    out = {}
    for i in range(count):
        out.setdefault(names[previous[i]], []).append((names[following[i]], probability[i]))
    return out, names


def main():
    code = sys.argv[1]
    wanted = sys.argv[2:]
    model, words = load(code)
    if not wanted:
        print(f"{code}: {len(model):,} words with followers, {len(words):,} in the dictionary")
        return
    for word in wanted:
        followers = model.get(word)
        if followers is None:
            print(f"{word!r}: not in the dictionary")
            continue
        print(f"{word!r}: {len(followers)} followers")
        for follower, probability in followers[:12]:
            print(f"    {follower:<22} {probability:>3}")


if __name__ == "__main__":
    main()
