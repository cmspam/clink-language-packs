# The Mongolian keyboard in Clink

Three repositories, all public, all under `cmspam`:

| Repository | What it gives |
|---|---|
| `cmspam/clink-language-packs` | The `mn` language pack: dictionary, next-word model, neural model, emoji metadata, input-method table |
| `cmspam/clink-layouts` | Two Mongolian Cyrillic keyboard layouts |
| `cmspam/clink-plugins` | The "Mongolian Latin" plugin, which writes Cyrillic while you type Latin |

## In Clink

**1. Add the repositories.** General → Repositories, then add each one:

```
cmspam/clink-language-packs
cmspam/clink-layouts
cmspam/clink-plugins
```

**2. Install the language.** Languages, then find Mongolian under Community and
install it. It appears as `mn`; the app knows that code from the locale table,
so it should read as Mongolian.

**3. Install the layout.** Customize → Layout → Layout packs, pick the
`cmspam/clink-layouts` repository, and install one of:

- **Mongolian Cyrillic** (13/12/10). The three letter rows, with the
  number-row letters е, ь and щ at the ends of rows two and three.
- **Mongolian Cyrillic (number row together)** (13/11/11). The same, with е, ь
  and щ kept together at the end of the bottom row.

Then set it as the arrangement for the Mongolian language. Layouts belong to a
language, so open the Mongolian language and choose the layout there.

**4. Install the plugin** (needs Clink Pro, and asks you to trust the
repository's code). Plugins → `cmspam/clink-plugins` → "Mongolian Latin".

The plugin only acts when the active language is Mongolian. It has two
switches: "Write Mongolian in Cyrillic" turns it off entirely, and "Convert
in every language" makes it act whatever language is selected.

## The two ways to type

**Cyrillic directly.** With the layout installed, the keys are Mongolian
letters. Nothing to learn, nothing ambiguous. The pack's dictionary and
next-word model drive the suggestions.

**Latin in, Cyrillic out.** With the plugin installed and a Latin arrangement
selected, type `mongol` and the plugin offers `монгол` in the suggestion bar,
and commits it when you press space. `ch` gives ч, `sh` gives ш, `shch` gives
щ, `ts` gives ц, and an apostrophe gives the hard sign, so `yav'ya` is
`явъя`. The words Latin cannot express (ө, ү, the soft sign) are resolved from
the dictionary and the surrounding word, which is why `u` can come out as
either у or ү.

The plugin comes in two shapes: Mongolian Latin Live writes the word in
Cyrillic letter by letter as you type, so the keyboard's own dictionary,
next-word model and spelling help read Cyrillic and answer with it, and
Mongolian Latin writes the word in Cyrillic when space ends it. The live shape
is what makes the prediction, the several choices in the bar and the spelling
help work in Latin, because those come from the language pack and the pack has
nothing to match in Latin text.

Measured on held-out Mongolian typed in Latin, the plugin writes 92.7% of words
correctly. Words the dictionary holds are 98.6% correct; words it does not are
69% correct, written from the word's own vowels.

A bare y is read as the palatal vowel as well, so yvah gives явах and goy
gives гоё. The usual spellings, ya, yu and yo, still win.

The two work together: the plugin writes the Cyrillic, and the pack's
dictionary then corrects and predicts it as ordinary Mongolian text.

## What is in the pack

The dictionary holds 300,000 word forms, so the rare ones a suffix produces
(`явал`, `яваасан`, `болохгүй`) are in it as well as the common ones. It
covers every Mongolian word the corpus shows three or more times, which is
98.8% of the words people write.

The next-word model was built from Mongolian web text, which is why it
suggests "байна" after "сайн" and not the tail of a name. An encyclopedia gets
that wrong: there "сайна" is mostly a name, and "байна" follows it eight times
in a million, while on the web "сайн байна" is everywhere.

The neural model was trained on the same text and is compiled to Core ML in
CI, because coremltools only writes the package on macOS. It is what the
keyboard uses when the bigram has nothing to offer.

The corpus is Mongolian Wikipedia (CC BY-SA 4.0), Tatoeba's Mongolian
sentences (CC BY 2.0 FR) and mC4's Mongolian web text (ODC-BY 1.0). Every
source is pinned by digest in `source/mn-receipt.json`, and the web text is
filtered so that Russian, Kazakh and Buryat pages do not leak into it.

## If the input-method table takes over

The pack also carries `mn.cime`, a table of Latin readings to Cyrillic
characters. Clink only applies this kind of table to its Chinese and Japanese
composition engines, so it will most likely do nothing. If Clink does treat
Mongolian as an input-method language and switches your board, remove
`Lexicons/mn.cime` from the pack and publish again.
