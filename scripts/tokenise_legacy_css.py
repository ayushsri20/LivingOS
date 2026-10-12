#!/usr/bin/env python3
"""
Replace the hard-coded legacy colours in the existing stylesheets with Panesar
tokens. Selectors, layout, dimensions and responsive rules are untouched — only
the colour values change.

Idempotent: running it twice is a no-op. Prints a per-file tally.
"""
import pathlib
import re
import sys

FRONTEND = pathlib.Path(__file__).resolve().parent.parent / "frontend"

# legacy value -> token
MAP = {
    # Muted text / borders
    "#5c564c": "var(--muted-text)",
    "#9d968a": "var(--muted-text)",
    # Semantic washes (toast + card tints)
    "#ffe0dc": "var(--error-wash)",
    "#ffe7e2": "var(--error-wash)",
    "#e8efff": "var(--action-wash)",
    "#e0f1e8": "var(--success-wash)",
    "#d8f0e5": "var(--success-wash)",
    # Semantic text
    "#8e1d14": "var(--error)",
    "#a82d23": "var(--error)",
    "#8a6a00": "var(--warning-ink)",
    "#176b45": "var(--success-ink)",
    # Ink alphas -> hairline scale
    "rgba(26, 26, 26, 0.54)": "var(--hairline-strong)",
    "rgba(26, 26, 26, 0.4)": "var(--hairline)",
    "rgba(26, 26, 26, 0.1)": "var(--hairline-faint)",
    "rgb(26 26 26 / 52%)": "var(--hairline-strong)",
    "rgb(26 26 26 / 48%)": "var(--hairline)",
    "rgb(26 26 26 / 18%)": "var(--hairline)",
    "rgb(26 26 26 / 5%)": "var(--hairline-faint)",
    # The old yellow hover -> gold identity wash
    "rgba(255, 204, 0, 0.08)": "var(--gold-wash)",
    "#ffcc00": "var(--champagne-gold)",
}

TOKEN_RE = re.compile(r"var\(--[a-z0-9-]+\)")


def convert(text):
    tally = {}
    for legacy, token in MAP.items():
        pattern = re.compile(re.escape(legacy), re.IGNORECASE)
        text, count = pattern.subn(token, text)
        if count:
            tally[legacy] = count
    return text, tally


def main():
    total = 0
    for name in ("components.css", "App.css"):
        path = FRONTEND / "src" / name
        original = path.read_text()
        updated, tally = convert(original)
        if updated != original:
            path.write_text(updated)
        total += sum(tally.values())
        print(f"{name}: {sum(tally.values())} replacements")
        for legacy, count in sorted(tally.items(), key=lambda kv: -kv[1]):
            print(f"    {count:>2}x  {legacy}  ->  {MAP[legacy]}")

    # Report anything still hard-coded so it can be reviewed by hand.
    print("\nRemaining hard-coded colours (review):")
    found = False
    for name in ("components.css", "App.css"):
        text = (FRONTEND / "src" / name).read_text()
        for match in re.finditer(r"#[0-9a-fA-F]{3,8}\b|rgba?\([^)]*\)|rgb\([^)]*\)", text):
            value = match.group(0)
            # Pure white on an accent is intentional and universal.
            if value.lower() in ("#fff", "#ffffff"):
                continue
            print(f"    {name}: {value}")
            found = True
    if not found:
        print("    none")

    print(f"\nTOTAL: {total} colour values tokenised")
    return 0


if __name__ == "__main__":
    sys.exit(main())
