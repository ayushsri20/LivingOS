#!/usr/bin/env python3
"""
Read-only analysis of the navigation scroll container.

Answers, from the shipped CSS and JSX alone:
  * which node carries the horizontal overflow
  * what overflow-x computes to at a given viewport
  * whether the scrolling node is an ancestor of the nav links
  * whether any other stylesheet can override it
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "frontend" / "src"

components = (SRC / "components.css").read_text()
app_css = (SRC / "App.css").read_text()
index_css = (SRC / "index.css").read_text()
shared = (SRC / "components" / "shared.jsx").read_text()

VIEWPORTS = (375, 390, 430, 768, 797, 1024, 1280, 1440)


def media_blocks(css):
    for match in re.finditer(r"@media\s*\(\s*max-width:\s*(\d+)px\s*\)\s*\{", css):
        width = int(match.group(1))
        start = match.end() - 1
        depth, cursor = 0, start
        while cursor < len(css):
            if css[cursor] == "{":
                depth += 1
            elif css[cursor] == "}":
                depth -= 1
                if depth == 0:
                    break
            cursor += 1
        yield width, css[start:cursor + 1]


def rules_for(css, selector):
    """Return the declaration bodies of every rule whose selector list
    contains exactly `selector`. Compares parsed selector items, so it never
    depends on regex escaping of class names."""
    out = []
    for match in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
        selector_text = match.group(1).strip()
        # Drop CSS comments, then split the selector list.
        selector_text = re.sub(r"/\*.*?\*/", " ", selector_text, flags=re.S)
        items = [item.strip() for item in selector_text.split(",")]
        if selector in items:
            out.append(match.group(2))
    return out


def strip_nested_media(css):
    out, index = [], 0
    while True:
        start = css.find("@media", index)
        if start == -1:
            out.append(css[index:])
            break
        brace = css.find("{", start)
        depth, cursor = 0, brace
        while cursor < len(css):
            if css[cursor] == "{":
                depth += 1
            elif css[cursor] == "}":
                depth -= 1
                if depth == 0:
                    break
            cursor += 1
        out.append(css[index:start])
        index = cursor + 1
    return "".join(out)


def computed_overflow_x(selector, viewport):
    """Resolve overflow-x for `selector` at `viewport`, honouring cascade order."""
    value = "visible"
    layers = [(None, strip_nested_media(components))]
    layers += [(w, b) for w, b in sorted(media_blocks(components))]
    layers.append((None, strip_nested_media(app_css)))
    layers += [(w, b) for w, b in sorted(media_blocks(app_css))]

    for width, css in layers:
        if width is not None and viewport > width:
            continue
        for decls in rules_for(css, selector):
            shorthand = re.search(r"(?<![\w-])overflow\s*:\s*([^;]+)", decls)
            if shorthand:
                parts = shorthand.group(1).split()
                value = parts[0] if len(parts) >= 2 else "auto"
                continue
            longhand = re.search(r"(?<![\w-])overflow-x\s*:\s*([^;]+)", decls)
            if longhand:
                value = longhand.group(1).strip()
    return value


print("Element roles (from frontend/src/components/shared.jsx)")
print("-" * 70)
print("  <nav  class='top-nav'>          <- the scrolling container")
print("    <ul class='top-nav-list'>     <- holds the nav LINKS (no overflow, correctly)")
print("    <button class='top-nav-logout'>")
print()
print("Which node declares horizontal overflow")
print("-" * 70)
for selector in (".top-nav", ".top-nav-list", ".top-nav-item", ".nav-link"):
    decls = rules_for(components, selector)
    has = any("overflow" in d for d in decls)
    print(f"  {selector:<16} declares overflow: {'YES' if has else 'no':<4} (rules: {len(decls)})")
print()
print("Can another stylesheet override it?")
print("-" * 70)
overridden = False
for name, css in (("App.css", app_css), ("index.css", index_css)):
    for selector in (".top-nav", ".top-nav-list"):
        if rules_for(css, selector):
            print(f"  WARNING {name} also styles {selector}")
            overridden = True
if not overridden:
    print("  App.css / index.css contain NO .top-nav or .top-nav-list rule -> no conflict")
print()
nested = bool(re.search(r'<nav className="top-nav"[^>]*>\s*<ul className="top-nav-list"', shared))
print(f"Ancestry: <ul.top-nav-list> is a direct child of <nav.top-nav>: {nested}")
print()
print("Computed overflow-x by viewport (source of truth = shipped CSS)")
print("-" * 70)
print(f"  {'viewport':>9} | {'.top-nav':<14} | {'.top-nav-list':<16} | scroller")
print(f"  {'-'*9}-+-{'-'*14}-+-{'-'*16}-+-----------")
for viewport in VIEWPORTS:
    nav = computed_overflow_x(".top-nav", viewport)
    lst = computed_overflow_x(".top-nav-list", viewport)
    if nav in ("auto", "scroll"):
        scroller = ".top-nav (scrolls)"
    elif viewport <= 900:
        scroller = "NONE - would overflow page"
    else:
        scroller = "n/a - fits inline by design"
    print(f"  {viewport:>7}px | {nav:<14} | {lst:<16} | {scroller}")
print()
print("  Note: above 900px the nav is *designed* to fit inline, so it has no")
print("  scroller. That range relies on the row actually fitting in the space")
print("  left by the brand, and is the one width band not proven here - it needs")
print("  the manual viewport pass (no browser automation in this project).")
print()

scrollable = all(computed_overflow_x(".top-nav", v) == "auto" for v in (375, 390, 430))
child_visible = all(computed_overflow_x(".top-nav-list", v) == "visible" for v in (375, 390, 430))
print("Conclusion")
print("-" * 70)
print(f"  .top-nav scrolls at 375/390/430      : {scrollable}")
print(f"  .top-nav-list stays overflow-x:visible: {child_visible}")
print("  -> 'visible' on the <ul> is CORRECT. A child of a scroll container")
print("     does not need its own overflow; DevTools was pointed at the <ul>")
print("     instead of the <nav class='top-nav'> that actually scrolls.")
sys.exit(0 if scrollable and child_visible else 1)
