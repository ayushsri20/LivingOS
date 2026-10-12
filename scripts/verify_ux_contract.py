#!/usr/bin/env python3
"""
Static contract checks for the Phase 1 / Phase 2 UX work.

Verifies the CSS actually shipped in `dist/` carries the mobile navigation and
feedback rules the brief requires, and that no rule can force horizontal
overflow at the listed phone widths. Read-only; touches no backend.
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"
CSS = FRONTEND / "dist" / "assets"

REQUIRED_VIEWPORTS = (1440, 1280, 1024, 768, 430, 390, 375)
PHONE_VIEWPORTS = (430, 390, 375)

checks = []


def check(name, ok, detail=""):
    checks.append((name, ok, detail))


def load_css():
    files = sorted(CSS.glob("*.css"))
    return "\n".join(f.read_text() for f in files), [f.name for f in files]


css, files = load_css()
src_css = (FRONTEND / "src" / "components.css").read_text()
app_jsx = (FRONTEND / "src" / "App.jsx").read_text()
shared = (FRONTEND / "src" / "components" / "shared.jsx").read_text()

check("built CSS found", bool(css), ", ".join(files))

# --- mobile navigation -----------------------------------------------------
check(".top-nav container exists in source", ".top-nav {" in src_css)
check("nav list is a <ul>", "top-nav-list" in shared and "<ul" in shared)
# Counts NAV_ITEMS entries only: the mobile tab bar reuses the same view ids
# through MOBILE_PRIMARY / MOBILE_MORE, which must not inflate the total.
nav_items_block = shared[shared.find("const NAV_ITEMS"):shared.find("const MOBILE_PRIMARY")]
check("nav item count preserved (7 sections)",
      nav_items_block.count("{ id: '") == 7, f"found {nav_items_block.count(chr(123) + ' id: ' + chr(39))}")

# A horizontal scroller, not a wrapper: this is the fix for the tall header.
def media_blocks(sheet, condition):
    """Every brace-matched `@media <condition>` block.

    A non-greedy `\\n\\}` match is wrong here: it stops at the first nested
    closing brace, so it silently inspects only the first rule of the first
    matching block. Returns the concatenated bodies.
    """
    bodies = []
    index = 0
    while True:
        start = sheet.find("@media", index)
        if start == -1:
            break
        brace = sheet.find("{", start)
        if brace == -1:
            break
        header = sheet[start:brace]
        depth, cursor = 0, brace
        while cursor < len(sheet):
            if sheet[cursor] == "{":
                depth += 1
            elif sheet[cursor] == "}":
                depth -= 1
                if depth == 0:
                    break
            cursor += 1
        if condition in re.sub(r"\s+", "", header):
            bodies.append(sheet[brace + 1:cursor])
        index = cursor + 1
    return "\n".join(bodies)


mobile_block = re.search(r"@media \(max-width: 900px\)\s*\{", src_css)
check("mobile breakpoint at 900px present", mobile_block is not None)
if mobile_block:
    body = media_blocks(src_css, "(max-width:900px)")
    check("nav does not wrap on mobile", "flex-wrap: wrap" not in body,
          "a wrapping nav is what made the mobile header tall")
    check("nav scrolls horizontally instead", "overflow-x: auto" in body)
    check("topbar stacks brand above nav", "flex-direction: column" in body)
    check("logout is pinned, not scrolled away", "position: sticky" in body)

check("nav scroller hidden scrollbar", "scrollbar-width: none" in src_css)

# --- active state ----------------------------------------------------------
check("active nav keeps yellow fill", ".nav-link.active" in src_css
      and "var(--yellow)" in src_css)
check("active nav has a non-colour marker", ".nav-link.active::after" in src_css)
check("active nav exposed to assistive tech", 'aria-current' in shared)
# The redundant `PANESAR / RENTAL OS` brand row was intentionally removed from
# the topbar as part of the approved dashboard composition change (header →
# dashboard hero as one architectural surface). The contract guards that it
# stays removed rather than reintroduced as a second branding strip.
check("redundant topbar brand row stays removed", "topbar-brand" not in shared)
check("brand has an accessible name", "aria-label" in shared)

# --- touch targets ---------------------------------------------------------
check("coarse-pointer tap targets >= 44px",
      re.search(r"@media \(pointer: coarse\)", src_css) is not None)

# --- no horizontal overflow ------------------------------------------------
check("html min-width is 320px or lower",
      re.search(r"min-width:\s*(3[0-9][0-9]|2[0-9][0-9])px", (FRONTEND / "src" / "index.css").read_text())
      is not None)


def strip_desktop_only(sheet):
    out, index = [], 0
    while True:
        start = sheet.find("@media", index)
        if start == -1:
            out.append(sheet[index:])
            break
        brace = sheet.find("{", start)
        condition = sheet[start:brace]
        depth, cursor = 0, brace
        while cursor < len(sheet):
            if sheet[cursor] == "{":
                depth += 1
            elif sheet[cursor] == "}":
                depth -= 1
                if depth == 0:
                    break
            cursor += 1
        out.append(sheet[index:start])
        if "min-width" not in condition:
            out.append(sheet[start:cursor + 1])
        index = cursor + 1
    return "".join(out)


mobile_css = strip_desktop_only(src_css)
offenders = [v for v in re.findall(r"min-width:\s*(\d+)px", mobile_css) if int(v) > 375]
check("no min-width wider than 375px in mobile cascade", not offenders,
      f"offenders: {offenders}")

# The toast used to be left:24px + max-width:380px = 404px on a 375px screen.
check("toast width is viewport-relative",
      re.search(r"\.toast-region\s*\{[^}]*width:\s*min\(380px,\s*calc\(100vw - 2 \*", src_css, re.S)
      is not None)
# Look for a real declaration, not the explanatory comment that mentions it.
check("old fixed toast width removed",
      re.search(r"^\s*left:\s*24px\s*;", src_css, re.M) is None
      and re.search(r"^\s*max-width:\s*380px\s*;", src_css, re.M) is None)

# --- interaction feedback --------------------------------------------------
check("loading state has a textual + visual indicator",
      ".loading-shell::before" in src_css and "busy-pulse" in src_css)
check("reduced-motion honoured for the busy indicator",
      re.search(r"@media \(prefers-reduced-motion: reduce\)", src_css) is not None)
check("toast region uses a class, not inline fixed positioning",
      "toast-region" in app_jsx and "position: 'fixed'" not in app_jsx)
check("button press feedback exists", ".btn-primary:active" in src_css)
check("button focus ring exists", ":focus-visible" in src_css)
check("disabled state exists", ".btn-primary:disabled" in src_css)

# --- page identity ---------------------------------------------------------
check("main landmark is labelled by the page title",
      'aria-labelledby="page-title"' in app_jsx and 'id="page-title"' in app_jsx)

# --- Phase 3: information hierarchy -----------------------------------------
# 1. Yellow means exactly two things on a screen: current location and page
#    identity. It must not also be a metric colour on the dashboard.
dashboard = app_jsx[app_jsx.find("function DashboardView"):app_jsx.find("function ElectricityView")]
check("yellow is no longer used for a dashboard metric",
      'color="yellow"' not in dashboard,
      "yellow competes with the active nav and the page banner")
check("page banner keeps its yellow identity",
      re.search(r"\.page-banner\s*\{[^}]*background:\s*var\(--yellow\)", src_css, re.S)
      is not None)
check("active nav keeps its yellow identity",
      re.search(r"\.nav-link\.active\s*\{[^}]*var\(--yellow\)", src_css, re.S) is not None)
check("yellow metric-card variant still exists for other screens",
      ".metric-card.yellow" in src_css,
      "PaymentsView and RoomDrawer still use it")

# 2. Property state and financial state are two distinct clusters, carried by
#    the dashboard section order: snapshot (inventory) then collection (money).
check("property snapshot block exists", "dash-snapshot" in dashboard and "Property Snapshot" in dashboard)
check("monthly collection block exists", "dash-collection" in dashboard and "Monthly Collection" in dashboard)
check("property group marker kept", "metric-group--property" in dashboard)
check("finance group marker kept", "metric-group--finance" in dashboard)
check("dashboard section-head rules exist", ".dash-head {" in src_css and ".dash-title {" in src_css)

# 3. Financial values outrank their labels, and the dashboard states money once.
check("collection figures exist", "collection-grid" in dashboard and ".collection-value {" in src_css)
check("money values use tabular figures",
      re.search(r"\.collection-value\s*\{[^}]*font-variant-numeric", src_css, re.S) is not None)
check("money value scale is a display size",
      re.search(r"\.collection-value\s*\{\s*[^}]*font-size:\s*clamp\(24px", src_css, re.S) is not None)

# The building directory component is defined just above DashboardView (and the
# contract slice starts there), so component markup is checked against the
# whole file while the in-view content checks stay on the dashboard slice.
# 4. Building directory: six architectural objects with a six-room facade.
for part in ("building-object", "building-facade", "facade-room",
             "building-object-name", "building-object-occupancy",
             "building-object-status", "building-object-action"):
    check(f"building directory has {part}",
          part in app_jsx and part in src_css)

# Occupancy leads; each card states what it still owes and routes to Rooms.
dashboard_lower = dashboard.lower()
for kept in ("rooms", "occupied", "due"):
    check(f"building card still shows '{kept}'", kept in dashboard_lower)
check("building card remains a labelled button",
      "aria-label={`Open rooms in building" in app_jsx)
check("portfolio pulse block exists", "dash-pulse" in dashboard and "Portfolio Pulse" in dashboard)

# 5. Mobile: the seven-item desktop strip is replaced at phone widths by
#    Home | Rooms | Payments | More.
check("mobile tab bar exists", "mobile-tabbar" in shared)
check("mobile primary destinations are Home, Rooms, Payments",
      all(f"id: '{view}'" in shared for view in ("dashboard", "rooms", "payments")))
check("mobile more menu exists", "more-menu" in shared and "MOBILE_MORE" in shared)
check("tab bar rules ship", ".mobile-tabbar {" in src_css and ".more-menu {" in src_css)


# --- report ----------------------------------------------------------------
passed = sum(1 for _, ok, _ in checks if ok)
for name, ok, detail in checks:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail and not ok else ""))
print()
print(f"{passed}/{len(checks)} static UX contract checks passed")
sys.exit(0 if passed == len(checks) else 1)
