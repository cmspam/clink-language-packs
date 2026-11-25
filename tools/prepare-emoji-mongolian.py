#!/usr/bin/env python3
"""Build Lexicons/mn.emoji.json from the Unicode CLDR Mongolian annotations.

The CLDR release and the Unicode emoji list are both pinned, so the file is
reproducible. The annotation keywords become the aliases a person can type,
and the spoken-name annotation becomes the localized name the predictive bar
shows. Only the glyphs Clink's keyboard can produce are included.

The CLDR data is under the Unicode licence, which the repository already
carries in UNICODE-LICENSE.txt.

Usage: python3 tools/prepare-emoji-mongolian.py
"""
import hashlib
import json
import pathlib
import urllib.request
import xml.etree.ElementTree as etree

ROOT = pathlib.Path(__file__).resolve().parents[1]
LEXICONS = ROOT / "Lexicons"
SOURCE = ROOT / "source"
CLDR = "https://raw.githubusercontent.com/unicode-org/cldr/release-48/common"
EMOJI_LIST = "https://unicode.org/Public/emoji/latest/emoji-test.txt"
EMOJI_SHA256 = "8f3735cda1f92a779d78af67cf86066bb1f07143dc22f2ac29394d9bc57ab21a"
CODE = "mn"

# Function words that should not bring up an emoji on their own.
STOPWORDS = ["ба", "болон", "гэж", "бөгөөд", "мөн", "юм", "нь", "ч", "энэ", "тэр"]
# Words worth listing first, ahead of the CLDR wording. The country name for
# the flag helps when the system locale does not give a localized one.
EXTRA_ALIASES = {"🇲🇳": ["монгол"]}
# Skin-tone variants are the same emoji, so they are never separate keys.
TONES = set(range(0x1F3FB, 0x1F400))


def neutral(glyph: str) -> str:
    return "".join(c for c in glyph if ord(c) != 0xFE0F and ord(c) not in TONES)


def download(url: str, name: str, digest: str = "") -> bytes:
    path = SOURCE / ".cache" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        with urllib.request.urlopen(url) as response:
            path.write_bytes(response.read())
    data = path.read_bytes()
    if digest and hashlib.sha256(data).hexdigest() != digest:
        raise SystemExit(f"{name}: digest changed; check whether Unicode published a new emoji list.")
    return data


def keyboard_glyphs(data: bytes) -> set[str]:
    """The neutral, fully qualified glyphs a keyboard can produce."""
    glyphs = set()
    for line in data.decode("utf-8").splitlines():
        if "; fully-qualified" not in line or "#" not in line:
            continue
        points = [int(point, 16) for point in line.split(";", 1)[0].strip().split()]
        if any(point in TONES for point in points):
            continue
        glyphs.add(neutral("".join(chr(point) for point in points)))
    return glyphs


def main() -> None:
    allowed = keyboard_glyphs(download(EMOJI_LIST, "emoji-test.txt", EMOJI_SHA256))
    aliases: dict[str, list[str]] = {}
    names: dict[str, str] = {}
    provenance = []
    for directory in ("annotations", "annotationsDerived"):
        url = f"{CLDR}/{directory}/{CODE}.xml"
        data = download(url, f"cldr/{directory}/{CODE}.xml")
        provenance.append({"source": url, "sha256": hashlib.sha256(data).hexdigest()})
        for element in etree.fromstring(data).findall(".//annotation"):
            raw = element.get("cp", "")
            if not raw or not element.text:
                continue
            # A skin-tone variant is the same emoji with extra keywords. Drop
            # it rather than folding its wording into the plain one.
            if any(ord(char) in TONES for char in raw):
                continue
            glyph = neutral(raw)
            if glyph not in allowed:
                continue
            if element.get("type") == "tts":
                names.setdefault(glyph, element.text.strip())
                continue
            words = [word.strip() for word in element.text.split("|") if word.strip()]
            aliases.setdefault(glyph, []).extend(words)

    # Keep the first occurrence of each word, so the annotation order stands.
    cleaned = {glyph: list(dict.fromkeys(words)) for glyph, words in aliases.items() if words}
    for glyph, words in EXTRA_ALIASES.items():
        if glyph in cleaned:
            cleaned[glyph] = list(dict.fromkeys(words + cleaned[glyph]))
    spoken = {glyph: name for glyph, name in names.items() if glyph in cleaned and name}

    LEXICONS.mkdir(exist_ok=True)
    (LEXICONS / f"{CODE}.emoji.json").write_text(json.dumps({
        "version": 1,
        "aliases": dict(sorted(cleaned.items())),
        "names": dict(sorted(spoken.items())),
        "stopwords": STOPWORDS,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    (SOURCE / "mn-emoji-receipt.json").write_text(json.dumps({
        "language": {"code": CODE, "name": "Mongolian"},
        "sources": provenance + [{
            "source": EMOJI_LIST,
            "sha256": EMOJI_SHA256,
            "role": "the set of glyphs Clink's keyboard can produce",
        }],
        "licence": "Unicode-3.0 (CLDR annotations and emoji data)",
        "derived": {
            "aliases": len(cleaned),
            "names": len(spoken),
            "stopwords": STOPWORDS,
            "extraAliases": EXTRA_ALIASES,
        },
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(cleaned):,} aliases and {len(spoken):,} names.")


if __name__ == "__main__":
    main()
