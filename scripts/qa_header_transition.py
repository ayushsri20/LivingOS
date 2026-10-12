"""Measure the Dashboard header -> hero transition and grid alignment.

Logs in, opens the Dashboard, and reports at each required viewport:
  - left/right edges of the Panesar header (.plh), the nav row (.panesar-bar),
    the Dashboard hero (.page-banner) and the content grid (.content-wrap)
  - the vertical gaps between them
  - horizontal overflow

Run:  .venv-2/bin/python scripts/qa_header_transition.py
Exit: 0 when no width overflows and the hero edges match the content grid.
"""

import os
import sys

from playwright.sync_api import sync_playwright

BASE = os.environ.get("QA_URL", "http://127.0.0.1:5173")
WIDTHS = [390, 430, 768, 1024, 1280, 1440]
SHOTS = "/tmp/hdr-qa"
# How far an edge may sit from the content grid before it counts as a
# misalignment. Sub-pixel rounding and fractional vw padding land here.
TOL = 1.5

MEASURE_JS = """() => {
  const rect = (sel) => {
    const el = document.querySelector(sel);
    if (!el) return null;
    const b = el.getBoundingClientRect();
    if (b.width === 0 && b.height === 0) return null;
    return {l: +b.left.toFixed(1), r: +b.right.toFixed(1),
            w: +b.width.toFixed(1), t: +b.top.toFixed(1),
            h: +b.height.toFixed(1)};
  };
  // .content-wrap is a full-width box whose padding forms the grid, so the
  // content edges are inset from its border box by the computed padding.
  const grid = (() => {
    const el = document.querySelector('.content-wrap');
    if (!el) return null;
    const cs = getComputedStyle(el);
    const b = el.getBoundingClientRect();
    const pl = parseFloat(cs.paddingLeft);
    const pr = parseFloat(cs.paddingRight);
    return {l: +(b.left + pl).toFixed(1), r: +(b.right - pr).toFixed(1),
            pl: +pl.toFixed(1), pr: +pr.toFixed(1),
            pt: +parseFloat(cs.paddingTop).toFixed(1)};
  })();
  const gap = (above, below) => {
    const a = document.querySelector(above);
    const b = document.querySelector(below);
    if (!a || !b) return null;
    return +(b.getBoundingClientRect().top
             - a.getBoundingClientRect().bottom).toFixed(1);
  };
  return {
    plh: rect('.plh'),
    bar: rect('.panesar-bar'),
    banner: rect('.page-banner'),
    wrap: rect('.content-wrap'),
    grid: grid,
    snapshot: rect('.snapshot-grid'),
    wrapMatchesSibling: (() => {
      const el = document.querySelector('.content-wrap');
      if (!el) return null;
      const prev = el.previousElementSibling;
      return {
        prevTag: prev ? prev.tagName : null,
        prevClass: prev ? prev.className : null,
        matches: el.matches('.topbar.panesar-topbar + .content-wrap'),
      };
    })(),
    bannerAbsent: !document.querySelector('.page-banner'),
    brandRowAbsent: !document.querySelector('.topbar-brand, .brand-button'),
    gap_plh_bar: gap('.plh', '.panesar-bar'),
    gap_bar_banner: gap('.panesar-bar', '.page-banner'),
    gap_header_banner: gap('.topbar', '.page-banner'),
    gap_banner_snapshot: gap('.page-banner', '.snapshot-grid'),
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  };
}"""


def main():
    os.makedirs(SHOTS, exist_ok=True)
    failures = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(f"{BASE}/login/", wait_until="domcontentloaded")
        page.fill('input[name="username"]', "admin")
        page.fill('input[name="password"]', "admin123")
        page.click('button[type="submit"]')
        page.wait_for_selector(".plh", timeout=20000)
        # Let the entry construction animation settle before measuring.
        page.wait_for_timeout(2400)
        page.wait_for_selector("#page-title:has-text('DASHBOARD')", timeout=10000)

        for width in WIDTHS:
            page.set_viewport_size({"width": width, "height": 900})
            page.wait_for_timeout(450)
            d = page.evaluate(MEASURE_JS)
            page.screenshot(path=f"{SHOTS}/dash-{width}.png")

            print(f"--- {width}px " + "-" * 40)
            for key in ("plh", "grid", "bar", "banner", "snapshot"):
                print(f"  {key:14} {d[key]}")
            print(f"  {'sibling':14} {d['wrapMatchesSibling']}")
            for key in ("gap_plh_bar", "gap_bar_banner",
                        "gap_header_banner", "gap_banner_snapshot"):
                print(f"  {key:14} {d[key]}")

            overflow = d["scrollWidth"] - d["clientWidth"]
            print(f"  {'scrollWidth':14} {d['scrollWidth']} "
                  f"(client {d['clientWidth']})")
            if overflow > 0:
                msg = f"horizontal overflow +{overflow}px"
                print(f"  !! FAIL {msg}")
                failures.append(f"{width}px: {msg}")

            # The header, hero and snapshot all live in the same grid, so their
            # outer edges must land on the same two vertical lines.
            for name, box in (("plh", d["plh"]), ("banner", d["banner"]),
                              ("snapshot", d["snapshot"])):
                if not box:
                    print(f"  !! FAIL {name} not rendered")
                    failures.append(f"{width}px: {name} missing")
                    continue
                dl = abs(box["l"] - d["grid"]["l"])
                dr = abs(box["r"] - d["grid"]["r"])
                if dl > TOL or dr > TOL:
                    msg = (f"{name} off grid by left {dl}px / right {dr}px")
                    print(f"  !! FAIL {msg}")
                    failures.append(f"{width}px: {msg}")

            # The removed brand row must not reappear, and the hero must stay.
            if not d["brandRowAbsent"]:
                msg = "redundant topbar brand row is back in the DOM"
                print(f"  !! FAIL {msg}")
                failures.append(f"{width}px: {msg}")
            if d["bannerAbsent"]:
                msg = "dashboard hero banner is not rendered"
                print(f"  !! FAIL {msg}")
                failures.append(f"{width}px: {msg}")

            # The transition must stay compact at every width, not just desktop.
            gap = d["gap_header_banner"]
            if gap is None or gap > 16:
                msg = f"header->hero gap too large ({gap}px)"
                print(f"  !! FAIL {msg}")
                failures.append(f"{width}px: {msg}")
            print()

            # The dashboard's trimmed top padding must not leak onto other pages:
        # every other view keeps .content-wrap's original top padding.
        page.set_viewport_size({"width": 1280, "height": 900})
        page.wait_for_timeout(300)
        for label in page.query_selector_all(".top-nav .nav-link"):
            text = (label.inner_text() or "").strip()
            if text in ("Home", "Dashboard"):
                continue  # the dashboard itself is the page being adjusted
            label.click()
            page.wait_for_timeout(700)
            pad = page.evaluate(
                "() => getComputedStyle(document.querySelector"
                "('.content-wrap')).paddingTop")
            print(f"  {text:14} content-wrap padding-top = {pad} (want 48px)")
            if pad != "48px":
                msg = f"{text} top padding changed to {pad} (expected 48px)"
                print(f"  !! FAIL {msg}")
                failures.append(msg)

        browser.close()

    print("=" * 52)
    if failures:
        print(f"FAILURES ({len(failures)}):")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("PASS: no horizontal overflow; hero and snapshot align to the grid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
