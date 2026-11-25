#!/usr/bin/env python3
"""Build a Clink .cngm next-word model from a plain sentence corpus.

Usage: python3 tools/build-next-word.py tok source/tok.txt source/tok.sentences.txt

The word list must be the same one used with build-pack.py. Put one complete
sentence per line in the corpus file. The result is Lexicons/tok.cngm.

Add --max-followers N to keep only the N most likely followers of each word.
A large corpus can otherwise produce millions of pairs that no keyboard ever
shows. The probabilities of the kept pairs are rescaled so they still sum to
one for each word.

Add --top-previous N to model only the N most frequent words as the word that
comes before another. A next-word suggestion is only useful after a word
people actually type, and the rare words contribute pairs nobody would see.

Add --min-length N to leave out words shorter than N letters, and
--keep-short LIST to keep particular short words anyway, written as a
comma-separated list. In Mongolian a one-letter word is a particle, and the
particles "л" and "ч" are what really follows a word, while the other
one-letter words in a web corpus are the tail of a broken word.
"""
import collections
import math
import pathlib
import re
import struct
import sys
import unicodedata

max_followers = 0
top_previous = 0
min_length = 1
keep_short = set()
arguments = sys.argv[1:]
for flag in ("--max-followers", "--top-previous", "--min-length", "--keep-short"):
    while flag in arguments:
        index = arguments.index(flag)
        if index + 1 >= len(arguments):
            raise SystemExit(f"{flag} needs a value.")
        value = arguments[index + 1]
        if flag == "--max-followers":
            max_followers = int(value)
        elif flag == "--top-previous":
            top_previous = int(value)
        elif flag == "--min-length":
            min_length = int(value)
        else:
            keep_short = {part.strip() for part in value.split(",") if part.strip()}
        del arguments[index:index + 2]
if len(arguments) != 3:
    raise SystemExit("Usage: python3 tools/build-next-word.py <code> <word-list.txt> <sentences.txt> [--max-followers N] [--top-previous N] [--min-length N] [--keep-short LIST]")
code, word_path, corpus_path = arguments[0], pathlib.Path(arguments[1]), pathlib.Path(arguments[2])
if not code or not code.replace("_", "").replace("-", "").isalnum():
    raise SystemExit("Use a short language code such as tok or pt_br.")

def word(value):
    value = unicodedata.normalize("NFC", value.strip().lower())
    return value if value and not any(char.isspace() for char in value) and any(char.isalpha() for char in value) else None

# This is the same bytewise word order build-pack.py writes into the CLEX file.
words = set()
frequency = {}
for raw in word_path.read_text(encoding="utf-8").splitlines():
    if raw.strip() and not raw.lstrip().startswith("#"):
        fields = raw.rsplit(maxsplit=1)
        candidate = word(fields[0])
        if candidate:
            words.add(candidate)
            try: frequency[candidate] = float(fields[1])
            except (IndexError, ValueError): frequency[candidate] = 1.0
ordered = sorted(words, key=lambda value: value.encode("utf-8"))
if not ordered: raise SystemExit("The word list contains no usable words.")
ids = {value: index for index, value in enumerate(ordered)}

# A next-word model only helps after a word people actually type. Restricting
# the previous words to the most frequent ones keeps the file to a size worth
# downloading without losing the suggestions anyone would use.
allowed = None
if top_previous:
    allowed = set(sorted(frequency, key=lambda value: (-frequency[value], value))[:top_previous])

pairs = collections.Counter()
for raw in corpus_path.read_text(encoding="utf-8").splitlines():
    # A Tatoeba export has id, language, sentence columns. A normal corpus line
    # has no tabs. In either case, the final field is the sentence text.
    sentence = raw.rsplit("\t", 1)[-1]
    tokens = [word(token) for token in re.findall(r'[^\s.,!?;:"“”‘’()\[\]{}]+', sentence)]
    tokens = [token for token in tokens if token in ids]
    tokens = [token for token in tokens
              if len(token) >= min_length or token in keep_short]
    if allowed is None:
        pairs.update(zip(tokens, tokens[1:]))
    else:
        pairs.update((first, second) for first, second in zip(tokens, tokens[1:])
                     if first in allowed)
if not pairs:
    raise SystemExit("No word pairs matched the word list. Check that the corpus and word list use the same spelling.")

totals = collections.Counter()
for (previous, _), count in pairs.items(): totals[previous] += count
# Pair groups must be previous-id ascending, then most frequent first.
ranked = sorted(pairs.items(), key=lambda item: (ids[item[0][0]], -item[1], ids[item[0][1]]))
if max_followers:
    # The ranked list is already grouped by previous word and ordered by count,
    # so keeping the first N of each group keeps that word's best followers.
    kept, group, taken = [], None, 0
    for item in ranked:
        identifier = ids[item[0][0]]
        if identifier != group:
            group, taken = identifier, 0
        if taken < max_followers:
            kept.append(item)
            taken += 1
    ranked = kept
    # Rescale, so the followers that survive still sum to one per word.
    totals = collections.Counter()
    for (previous, _), count in ranked: totals[previous] += count
blob = bytearray(b"CNGM" + struct.pack("<II", 1, len(ranked)))
for (previous, _), _count in ranked: blob += struct.pack("<I", ids[previous])
for (_, following), _count in ranked: blob += struct.pack("<I", ids[following])
for (previous, _), count in ranked:
    probability = count / totals[previous]
    blob.append(max(0, min(255, round((math.log10(probability) + 6) * 42))))

destination = pathlib.Path("Lexicons") / f"{code}.cngm"
destination.parent.mkdir(exist_ok=True)
destination.write_bytes(blob)
cap = f", at most {max_followers} followers per word" if max_followers else ""
top = f", modelling the {top_previous:,} most frequent words" if top_previous else ""
print(f"Built {destination} with {len(ranked):,} next-word pairs{cap}{top}.")
