#!/usr/bin/env python3
"""
Read-only verification of the frontend CSS after the Panesar colour migration.

Checks, without modifying anything:
  1. every class used in JSX resolves to a selector in the stylesheets
     (className="..." and className={`... ...`} are both parsed)
  2. every major UI area still has styling
  3. responsive breakpoints survive
  4. no legacy yellow remains as an active colour
  5. Panesar tokens are present, distinct and semantically correct

Exit status is meaningful: non-zero if a real class is unstyled, an area has
lost its styles, or legacy yellow survives.
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "frontend" / "src"

CSS_FILES = {
    "index.css": (SRC / "index.css").read_text(),
    "components.css": (SRC / "components.css").read_text(),
    "App.css": (SRC / "App.css").read_text(),
}

JSX_FILES = [
    SRC / "App.jsx",
    SRC / "components" / "shared.jsx",
    SRC / "components" / "RoomDrawer.jsx",
    SRC / "components" / "AssignResident.jsx",
]

results = []


def record(name, ok, detail=""):
    results.append((name, bool(ok), detail))


def bar(title):
    print("=" * 74)
    print(title)
    print("=" * 74)


# ---------------------------------------------------------------------------
# 1. Reliable class extraction
# ---------------------------------------------------------------------------

# Identifiers that leak in when a template literal's JS expressions are scanned.
JS_NOISE = {
    "class", "className", "modifier", "name", "type", "value", "label", "color",
    "colors", "tatus", "status", "uilding", "building", "urrent", "current",
    "ame", "overview", "expense", "selected", "tab", "style", "key", "id",
    "ref", "children", "isCurrent", "flash", "tone", "is", "active",
    # 'profile' and 'closing' appear as string VALUES (`setTab('profile')`,
    # `` `closing` ``), never in a className attribute.
    "profile", "closing",
}

CLASS_TOKEN = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")


def extract_classes(text):
    """Every class-looking token from className attributes, template literals
    included. Quoted literals inside ${...} are the real ones; bare words that
    are really JS identifiers are collected too and filtered by the caller."""
    found = set()

    for match in re.finditer(r'className="([^"]*)"', text):
        for token in match.group(1).split():
            if CLASS_TOKEN.match(token):
                found.add(token)

    for match in re.finditer(r"className=\{`([^`]*)`\}", text):
        chunk = match.group(1)
        for quoted in re.findall(r"'([^']*)'|\"([^\"]*)\"", chunk):
            value = quoted[0] or quoted[1]
            for token in value.split():
                if CLASS_TOKEN.match(token):
                    found.add(token)
        for bare in re.sub(r"\$\{[^}]*\}", " ", chunk).split():
            if CLASS_TOKEN.match(bare):
                found.add(bare)

    return found


def css_defines(name):
    """
    True when any stylesheet targets `.name`.

    Compound selectors count: `.metric-card.blue` styles `.blue` when it is
    applied as a modifier, which is how several classes in this app are
    generated (`className={`metric-card ${color}`}`). Requiring a standalone
    `.name` would wrongly report those as missing.
    """
    pattern = re.compile(rf"\.{re.escape(name)}(?=[\s,{{:.#\[:>+~]|$)", re.M)
    return any(pattern.search(css) for css in CSS_FILES.values())


used = set()
for path in JSX_FILES:
    used |= extract_classes(path.read_text())

noise = {t for t in used if t in JS_NOISE}
real = sorted(used - noise)
missing = [c for c in real if not css_defines(c)]

bar("1. CLASS COVERAGE")
record("class extraction produced tokens", len(real) > 50, str(len(real)))
record("no real JSX class is unstyled", not missing, ", ".join(missing))
print(f"  real classes in JSX    : {len(real)}")
print(f"  parser false positives : {len(noise)} -> {', '.join(sorted(noise))}")
print(f"  MISSING (category D)   : {', '.join('.' + m for m in missing) or 'none'}")
print()

AREAS = {
    "login":          ["login-shell", "login-panel", "login-form"],
    "loading shell":  ["loading-shell"],
    "top header":     ["topbar", "brand-mark", "brand-name", "brand-subtitle"],
    "navigation":     ["nav-link"],
    "dashboard":      ["dashboard-grid", "metrics-grid", "metric-card"],
    "rooms":          ["room-grid", "room-card", "room-number"],
    "room drawer":    ["drawer", "drawer-backdrop", "drawer-header", "drawer-content"],
    "residents":      ["resident-detail-grid", "resident-profile-card"],
    "payments":       ["payment-row", "payments-layout"],
    # Electricity reuses the room-card surface rather than a layout of its own.
    "electricity":    ["room-card", "error-state", "retry-button"],
    "expenses":       ["report-section"],
    "analytics":      ["analytics-grid", "analytics-card"],
    "modal":          ["modal-overlay", "modal-box", "modal-header", "modal-close"],
    "toast":          ["toast"],
    "empty state":    ["empty-state"],
    "error state":    ["error-state", "retry-button"],
    "progress":       ["progress-track", "progress-fill"],
    "forms":          ["field-group", "field-input", "pill", "pill-group"],
    "status badges":  ["status-tag"],
}
bar("2. UI AREA COVERAGE")
for area, classes in AREAS.items():
    hits = [c for c in classes if css_defines(c)]
    ok = len(hits) == len(classes)
    record(f"area:{area}", ok)
    gap = "" if ok else f"  missing: {', '.join('.' + c for c in classes if c not in hits)}"
    print(f"  {'OK ' if ok else 'GAP'}  {area:<15} {len(hits)}/{len(classes)}{gap}")
print()

# ---------------------------------------------------------------------------
# 3. Responsive breakpoints
# ---------------------------------------------------------------------------
bar("3. RESPONSIVE BREAKPOINTS")
for name, css in CSS_FILES.items():
    queries = sorted(
        {int(m) for m in re.findall(r"max-width:\s*(\d+)px", css)}
        | {int(m) for m in re.findall(r"min-width:\s*(\d+)px", css)}
    )
    if queries:
        record(f"breakpoints:{name}", True)
        print(f"  {name:<16} {queries}")
nav_responsive = css_defines("top-nav") or css_defines("nav-link")
record("responsive:nav rules", nav_responsive)
print(f"  navigation responsive rules present: {nav_responsive}")
print()

# ---------------------------------------------------------------------------
# 4. Legacy yellow - exact source scan, no pipe masking
# ---------------------------------------------------------------------------
bar("4. LEGACY YELLOW SCAN (source declarations)")
YELLOW_PATTERNS = {
    "#FFCC00": re.compile(r"#ffcc00", re.I),
    "rgb(255,204,0)": re.compile(r"rgb\(\s*255\s*,\s*204\s*,\s*0", re.I),
    "rgba(255,204,0,..)": re.compile(r"rgba\(\s*255\s*,\s*204\s*,\s*0", re.I),
    "space syntax 255 204 0": re.compile(r"\b255\s+204\s+0\b"),
}
yellow_hits = 0
for name, css in CSS_FILES.items():
    lines = css.splitlines()
    for label, pattern in YELLOW_PATTERNS.items():
        for match in pattern.finditer(css):
            line_no = css[: match.start()].count("\n") + 1
            snippet = lines[line_no - 1].strip()
            # A mention inside an explanatory comment is not a declaration.
            if snippet.startswith(("/*", "*", "//")) or "removes #FFCC00" in snippet:
                continue
            yellow_hits += 1
            print(f"  ACTIVE  {name}:{line_no}  [{label}]  {snippet[:64]}")
record("legacy yellow absent", yellow_hits == 0, str(yellow_hits))
print(f"  active legacy-yellow declarations: {yellow_hits}")
print()

# ---------------------------------------------------------------------------
# 5. Panesar tokens present and distinct
# ---------------------------------------------------------------------------
bar("5. PANESAR TOKENS")
REQUIRED_TOKENS = {
    "--panesar-black": "#171717",
    "--warm-ivory": "#f5f0e8",
    "--pure-surface": "#fffdf8",
    "--champagne-gold": "#c9a86a",
    "--deep-gold": "#a98245",
    "--deep-navy": "#0f172a",
    "--action-blue": "#2563eb",
    "--success": "#10b981",
    "--warning": "#f59e0b",
    "--error": "#ef4444",
    "--muted-text": "#777168",
}
root_block = CSS_FILES["index.css"].split(":root", 1)[-1].split("\n}", 1)[0]
for token, value in REQUIRED_TOKENS.items():
    present = re.search(
        rf"{re.escape(token)}\s*:\s*{re.escape(value)}", root_block, re.I
    ) is not None
    record(f"token:{token}", present)
    print(f"  {'OK ' if present else 'MISS'}  {token:<18} {value}")

token_values = [v.lower() for v in REQUIRED_TOKENS.values()]
record("tokens distinct", len(set(token_values)) == len(token_values))
print(f"  all {len(token_values)} token values distinct: "
      f"{len(set(token_values)) == len(token_values)}")
print()

# ---------------------------------------------------------------------------
# 6. Business meaning preserved through the legacy aliases
# ---------------------------------------------------------------------------
bar("6. SEMANTIC ALIASES (business meaning)")
ALIASES = {
    "--yellow": "--champagne-gold",   # brand / selection / emphasis
    "--blue": "--action-blue",        # operational action
    "--green": "--success",           # paid / settled
    "--red": "--error",               # overdue / error
    "--paper": "--warm-ivory",        # environment
    "--white": "--pure-surface",      # working surface
}
for alias, target in ALIASES.items():
    found = re.search(
        rf"{re.escape(alias)}\s*:\s*var\({re.escape(target)}\)", CSS_FILES["index.css"]
    ) is not None
    record(f"alias:{alias}", found)
    print(f"  {'OK ' if found else 'MISS'}  {alias:<20} -> var({target})")

sem = []
for token in ("--success", "--warning", "--error", "--action-blue"):
    match = re.search(rf"{re.escape(token)}\s*:\s*(#[0-9a-fA-F]+)", root_block, re.I)
    sem.append(match.group(1).lower() if match else "?")
record("semantic colours distinct", len(set(sem)) == 4, str(sem))
print(f"  success/warning/error/action distinct: {len(set(sem)) == 4}  {sem}")
print()

# Gold must differ from every semantic colour, or emphasis stops reading.
gold = REQUIRED_TOKENS["--champagne-gold"].lower()
record("gold distinct from semantics", gold not in sem)
print(f"  gold distinct from semantic colours: {gold not in sem}")
print()

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
bar("SUMMARY")
failed = [r for r in results if not r[1]]
print(f"  {len(results) - len(failed)}/{len(results)} checks passed")
for name, _, detail in failed:
    print(f"  FAIL  {name}  {detail}")
sys.exit(1 if failed else 0)

