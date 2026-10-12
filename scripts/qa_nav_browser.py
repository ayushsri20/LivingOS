#!/usr/bin/env python3
"""Browser-based navigation QA for the Panesar Living frontend.

Playwright interaction against the running Vite dev server (5173), Django
proxying API/login on 8000. Exercises every desktop tab, every mobile tab,
the MORE menu (open/close/navigate/outside/Escape), rapid taps, drawer and
modal open/close cycles, stacking/hit-testing, touch targets and horizontal
overflow at the required viewports.

Run:  .venv-2/bin/python scripts/qa_nav_browser.py
Exit: 0 when every check passes, 1 otherwise.
"""
import os
import sys

BASE = os.environ.get("QA_URL", "http://127.0.0.1:5173")
SHOTS = "/tmp/nav-qa"
os.makedirs(SHOTS, exist_ok=True)

DESKTOP_NAV = [
    ("Dashboard", "DASHBOARD"), ("Rooms", "ROOMS"), ("Payments", "PAYMENTS"),
    ("Residents", "RESIDENTS"), ("Electricity", "ELECTRICITY"),
    ("Expenses", "EXPENSES"), ("Analytics", "ANALYTICS"),
]
MOBILE_PRIMARY = [("Home", "DASHBOARD"), ("Rooms", "ROOMS"), ("Payments", "PAYMENTS")]
MOBILE_MORE = [
    ("Residents", "RESIDENTS"), ("Electricity", "ELECTRICITY"),
    ("Expenses", "EXPENSES"), ("Analytics", "ANALYTICS"),
]
DESKTOP_VIEWPORTS = [(1024, 768), (1280, 800), (1440, 900)]
MOBILE_VIEWPORTS = [(320, 640), (360, 800), (375, 812), (390, 844), (430, 932)]
TABLET_VIEWPORTS = [(768, 1024)]

RESULTS = []


def check(name, ok, extra=""):
    ok = bool(ok)
    RESULTS.append((name, ok, extra))
    print(("PASS  " if ok else "FAIL  ") + name + (f"  [{extra}]" if extra else ""))
    return ok


def banner_title(page):
    try:
        return page.locator("#page-title").inner_text(timeout=3000).strip()
    except Exception:
        return "<missing>"


def check_no_overflow(page, label):
    m = page.evaluate(
        """() => {const d = document.scrollingElement || document.documentElement;
            return {sw: d.scrollWidth, cw: d.clientWidth};}"""
    )
    check(f"no horizontal overflow {label}", m["sw"] <= m["cw"] + 1,
          f"scrollWidth={m['sw']} clientWidth={m['cw']}")


def active_desktop(page):
    try:
        return page.locator(".top-nav .nav-link.active").inner_text(timeout=2000).strip()
    except Exception:
        return "<none>"


def tap_desktop_tab(page, label, expected_title, viewport_label):
    try:
        page.locator(".top-nav .nav-link", has_text=label).first.click(timeout=5000)
        page.wait_for_selector(f"#page-title:has-text('{expected_title}')", timeout=5000)
        check(f"desktop tab '{label}' -> {expected_title} @ {viewport_label}",
              banner_title(page) == expected_title and active_desktop(page) == label,
              f"title={banner_title(page)} active={active_desktop(page)}")
    except Exception as exc:
        check(f"desktop tab '{label}' -> {expected_title} @ {viewport_label}",
              False, str(exc)[:120])


def desktop_phase(page):
    for w, h in DESKTOP_VIEWPORTS:
        label = f"{w}x{h}"
        page.set_viewport_size({"width": w, "height": h})
        page.goto(BASE, wait_until="domcontentloaded")
        page.wait_for_selector(".top-nav .nav-link", timeout=10000)
        check_no_overflow(page, f"@ {label}")
        check(f"desktop nav visible, tabbar hidden @ {label}",
              page.locator(".top-nav").is_visible()
              and not page.locator(".mobile-tabbar").is_visible())

        for nav_label, title in DESKTOP_NAV:
            tap_desktop_tab(page, nav_label, title, label)

        try:
            page.locator(".top-nav .nav-link", has_text="Payments").first.focus()
            page.keyboard.press("Enter")
            page.wait_for_selector("#page-title:has-text('PAYMENTS')", timeout=5000)
            check(f"keyboard Enter activates desktop tab @ {label}", True)
        except Exception as exc:
            check(f"keyboard Enter activates desktop tab @ {label}", False, str(exc)[:120])

        try:
            page.locator(".top-nav .nav-link", has_text="Rooms").first.click()
            page.locator(".top-nav .nav-link", has_text="Analytics").first.click()
            page.locator(".top-nav .nav-link", has_text="Dashboard").first.click()
            page.wait_for_selector("#page-title:has-text('DASHBOARD')", timeout=5000)
            check(f"rapid successive desktop taps settle @ {label}",
                  banner_title(page) == "DASHBOARD" and active_desktop(page) == "Dashboard")
        except Exception as exc:
            check(f"rapid successive desktop taps settle @ {label}", False, str(exc)[:120])

        page.screenshot(path=f"{SHOTS}/desktop-{label}.png")


def drawer_and_modal_cycle(page):
    label = "1280x800"
    page.set_viewport_size({"width": 1280, "height": 800})
    try:
        page.locator(".top-nav .nav-link", has_text="Rooms").first.click()
        page.wait_for_selector(".room-grid .room-card", timeout=8000)
        page.locator(".room-grid .room-card").first.click()
        page.wait_for_selector(".drawer", timeout=5000)
        zs = page.evaluate(
            """() => {
                const n = (s) => {const e = document.querySelector(s); if (!e) return null;
                    const z = Number(getComputedStyle(e).zIndex);
                    return Number.isFinite(z) ? z : null;};
                return {drawer: n('.drawer'), backdrop: n('.drawer-backdrop'),
                        topbar: n('.topbar'), tabbar: n('.mobile-tabbar')};
            }"""
        )
        check(f"drawer above header/tabbar stacking @ {label}",
              zs["drawer"] > zs["topbar"] and zs["backdrop"] > zs["topbar"]
              and (zs["tabbar"] is None or zs["drawer"] > zs["tabbar"]),
              str(zs))
        page.click(".drawer-backdrop", position={"x": 6, "y": 6})
        page.wait_for_selector(".drawer", state="detached", timeout=5000)
        check(f"drawer backdrop click closes drawer @ {label}", True)
    except Exception as exc:
        check(f"drawer open/close cycle @ {label}", False, str(exc)[:140])
        page.keyboard.press("Escape")

    try:
        page.locator(".top-nav .nav-link", has_text="Dashboard").first.click()
        page.wait_for_selector("#page-title:has-text('DASHBOARD')", timeout=5000)
        check(f"navigation responsive after drawer close @ {label}", True)
    except Exception as exc:
        check(f"navigation responsive after drawer close @ {label}", False, str(exc)[:140])

    try:
        page.locator(".top-nav .nav-link", has_text="Expenses").first.click()
        page.wait_for_selector("button:has-text('RECORD EXPENSE')", timeout=8000)
        page.click("button:has-text('RECORD EXPENSE')")
        page.wait_for_selector(".modal-overlay .modal-box", timeout=5000)
        page.click(".modal-close")
        page.wait_for_selector(".modal-overlay", state="detached", timeout=5000)
        check(f"modal close button dismisses modal @ {label}", True)
    except Exception as exc:
        check(f"modal open/close cycle @ {label}", False, str(exc)[:140])
        page.keyboard.press("Escape")

    try:
        page.locator(".top-nav .nav-link", has_text="Payments").first.click()
        page.wait_for_selector("#page-title:has-text('PAYMENTS')", timeout=5000)
        check(f"navigation responsive after modal close @ {label}", True)
    except Exception as exc:
        check(f"navigation responsive after modal close @ {label}", False, str(exc)[:140])

    style = page.evaluate("() => document.body.style.overflow")
    check(f"body scroll restored after overlays @ {label}",
          style in ("", "visible", "auto", "scroll"), f"overflow={style!r}")


def login(page):
    page.goto(BASE, wait_until="domcontentloaded")
    page.wait_for_selector("button.pl-enter", timeout=15000)
    page.click("button.pl-enter")
    page.wait_for_selector("#login-username", timeout=15000)
    page.fill("#login-username", "admin")
    page.fill("#login-password", "admin123")
    page.click(".pl-submit")
    page.wait_for_selector(".page-banner", timeout=20000)
    page.wait_for_selector("#page-title", timeout=10000)
    check("login reaches authenticated shell", True)


def more_menu_cycle(page, label):
    toggle = ".mobile-tabbar >> text=More"
    try:
        page.click(toggle)
        page.wait_for_selector(".more-menu", timeout=4000)
        check(f"More menu opens @ {label}", page.locator(".more-menu").is_visible())
    except Exception as exc:
        check(f"More menu opens @ {label}", False, str(exc)[:120])
        return

    # Toggle again must CLOSE it (regression: pointerdown/click double-toggle
    # used to close then immediately re-open the sheet).
    try:
        page.click(toggle)
        page.wait_for_selector(".more-menu", state="detached", timeout=4000)
        check(f"More toggle closes an open menu @ {label}", True)
    except Exception as exc:
        check(f"More toggle closes an open menu @ {label}", False, str(exc)[:120])

    try:
        page.click(toggle)
        page.wait_for_selector(".more-menu", timeout=4000)
        page.keyboard.press("Escape")
        page.wait_for_selector(".more-menu", state="detached", timeout=4000)
        check(f"Escape dismisses More menu @ {label}", True)
    except Exception as exc:
        check(f"Escape dismisses More menu @ {label}", False, str(exc)[:120])

    try:
        page.click(toggle)
        page.wait_for_selector(".more-menu", timeout=4000)
        page.click("h1#page-title", force=True)
        page.wait_for_selector(".more-menu", state="detached", timeout=4000)
        check(f"outside tap dismisses More menu @ {label}", True)
    except Exception as exc:
        check(f"outside tap dismisses More menu @ {label}", False, str(exc)[:120])


def mobile_more_navigation(page, label):
    for item, title in MOBILE_MORE:
        try:
            page.click(".mobile-tabbar >> text=More")
            page.wait_for_selector(".more-menu", timeout=4000)
            page.click(f".more-menu button:text-is('{item}')")
            page.wait_for_selector(f"#page-title:has-text('{title}')", timeout=5000)
            gone = page.locator(".more-menu").count() == 0
            check(f"More -> {item} navigates & menu closes @ {label}",
                  banner_title(page) == title and gone,
                  f"title={banner_title(page)} menu_open={not gone}")
        except Exception as exc:
            check(f"More -> {item} navigates & menu closes @ {label}",
                  False, str(exc)[:140])
            page.keyboard.press("Escape")



def mobile_phase(page):
    for w, h in MOBILE_VIEWPORTS:
        label = f"{w}x{h}"
        page.set_viewport_size({"width": w, "height": h})
        page.goto(BASE, wait_until="domcontentloaded")
        page.wait_for_selector(".mobile-tabbar", timeout=10000)
        check_no_overflow(page, f"@ {label}")
        check(f"mobile: top-nav hidden, bottom tabbar visible @ {label}",
              not page.locator(".top-nav").is_visible()
              and page.locator(".mobile-tabbar").is_visible())

        # Fixed nav is not obscured: hit-test the centre of every tab.
        obscured = page.evaluate(
            """() => {
                const bar = document.querySelector('.mobile-tabbar');
                if (!bar) return 'no tabbar';
                for (const btn of bar.querySelectorAll('button')) {
                    const r = btn.getBoundingClientRect();
                    const hit = document.elementFromPoint(
                        r.left + r.width / 2, r.top + r.height / 2);
                    if (!hit || !(btn === hit || btn.contains(hit))) {
                        return btn.textContent.trim() + ' hit='
                            + (hit && (hit.className || hit.tagName));
                    }
                }
                return '';
            }"""
        )
        check(f"bottom nav tabs hit-testable @ {label}", obscured == "", obscured)

        small = page.evaluate(
            """() => {
                const bad = [];
                for (const btn of document.querySelectorAll('.mobile-tab')) {
                    const r = btn.getBoundingClientRect();
                    if (r.height < 43.5)
                        bad.push(btn.textContent.trim() + ':' + Math.round(r.height));
                }
                return bad.join(',');
            }"""
        )
        check(f"mobile tab touch targets >= 44px @ {label}", small == "", small)

        pad = page.evaluate(
            "() => Number.parseFloat("
            "getComputedStyle(document.querySelector('.page-shell')).paddingBottom) || 0"
        )
        bar_h = page.evaluate(
            "() => document.querySelector('.mobile-tabbar').getBoundingClientRect().height"
        )
        check(f"content padding reserves tabbar space @ {label}",
              pad + 0.5 >= bar_h - 8,
              f"paddingBottom={pad} barHeight={round(bar_h, 1)}")

        for tab, title in MOBILE_PRIMARY:
            try:
                page.click(f".mobile-tabbar >> text={tab}")
                page.wait_for_selector(f"#page-title:has-text('{title}')", timeout=5000)
                active = page.evaluate(
                    """() => {const a = document.querySelector('.mobile-tab.is-active');
                        return a ? a.textContent.trim() : '<none>';}"""
                )
                expected = "Home" if tab == "Home" else tab
                check(f"mobile tab '{tab}' -> {title} & active @ {label}",
                      banner_title(page) == title and active == expected,
                      f"title={banner_title(page)} active={active}")
            except Exception as exc:
                check(f"mobile tab '{tab}' -> {title} & active @ {label}",
                      False, str(exc)[:140])

        check_no_overflow(page, f"after primary tabs @ {label}")
        more_menu_cycle(page, label)
        mobile_more_navigation(page, label)
        mobile_phase_tail(page, label, w, h)



def mobile_phase_tail(page, label, w, h):
    # Rapid successive taps must settle on the last destination.
    try:
        page.click(".mobile-tabbar >> text=Payments")
        page.click(".mobile-tabbar >> text=Rooms")
        page.click(".mobile-tabbar >> text=Home")
        page.wait_for_selector("#page-title:has-text('DASHBOARD')", timeout=5000)
        check(f"rapid successive mobile taps settle correctly @ {label}",
              banner_title(page) == "DASHBOARD")
    except Exception as exc:
        check(f"rapid successive mobile taps settle correctly @ {label}",
              False, str(exc)[:140])

    try:
        page.click(".mobile-tabbar >> text=Rooms")
        page.wait_for_selector("#page-title:has-text('ROOMS')", timeout=5000)
        check(f"nav responsive immediately after rapid taps @ {label}", True)
    except Exception as exc:
        check(f"nav responsive immediately after rapid taps @ {label}",
              False, str(exc)[:140])

    check_no_overflow(page, f"final @ {label}")
    page.screenshot(path=f"{SHOTS}/mobile-{label}.png")

    # Drawer + modal cycle on a representative phone width (375x812).
    if (w, h) == (375, 812):
        phone_drawer_modal(page, label)


def phone_drawer_modal(page, label):
    try:
        page.click(".mobile-tabbar >> text=Rooms")
        page.wait_for_selector(".room-grid .room-card", timeout=8000)
        page.locator(".room-grid .room-card").first.click()
        page.wait_for_selector(".drawer", timeout=5000)
        zs = page.evaluate(
            """() => {
                const n = (s) => {const e = document.querySelector(s); if (!e) return null;
                    const z = Number(getComputedStyle(e).zIndex);
                    return Number.isFinite(z) ? z : null;};
                return {drawer: n('.drawer'), backdrop: n('.drawer-backdrop'),
                        tabbar: n('.mobile-tabbar')};
            }"""
        )
        check(f"mobile drawer stacks above tabbar @ {label}",
              zs["drawer"] > zs["tabbar"] and zs["backdrop"] > zs["tabbar"], str(zs))
        page.screenshot(path=f"{SHOTS}/mobile-drawer-{label}.png")
        page.click(".drawer-backdrop", position={"x": 4, "y": 4})
        page.wait_for_selector(".drawer", state="detached", timeout=5000)
        check(f"mobile drawer backdrop closes @ {label}", True)
    except Exception as exc:
        check(f"mobile drawer open/close @ {label}", False, str(exc)[:140])
        page.keyboard.press("Escape")

    try:
        page.click(".mobile-tabbar >> text=Home")
        page.wait_for_selector("#page-title:has-text('DASHBOARD')", timeout=5000)
        check(f"mobile nav responsive after drawer close @ {label}", True)
    except Exception as exc:
        check(f"mobile nav responsive after drawer close @ {label}", False, str(exc)[:140])

    try:
        page.click(".mobile-tabbar >> text=More")
        page.wait_for_selector(".more-menu", timeout=4000)
        page.click(".more-menu button:text-is('Expenses')")
        page.wait_for_selector("#page-title:has-text('EXPENSES')", timeout=5000)
        page.click("button:has-text('RECORD EXPENSE')")
        page.wait_for_selector(".modal-overlay .modal-box", timeout=5000)
        page.screenshot(path=f"{SHOTS}/mobile-modal-{label}.png")
        page.click(".modal-close")
        page.wait_for_selector(".modal-overlay", state="detached", timeout=5000)
        page.click(".mobile-tabbar >> text=Rooms")
        page.wait_for_selector("#page-title:has-text('ROOMS')", timeout=5000)
        check(f"mobile nav responsive after modal close @ {label}", True)
    except Exception as exc:
        check(f"mobile modal cycle @ {label}", False, str(exc)[:140])



def tablet_phase(page):
    for w, h in TABLET_VIEWPORTS:
        label = f"{w}x{h}"
        page.set_viewport_size({"width": w, "height": h})
        page.goto(BASE, wait_until="domcontentloaded")
        page.wait_for_selector(".mobile-tabbar", timeout=10000)
        check_no_overflow(page, f"@ {label}")
        check(f"tablet uses bottom tabbar (top-nav hidden) @ {label}",
              page.locator(".mobile-tabbar").is_visible()
              and not page.locator(".top-nav").is_visible())
        try:
            page.click(".mobile-tabbar >> text=Payments")
            page.wait_for_selector("#page-title:has-text('PAYMENTS')", timeout=5000)
            check(f"tablet tab navigation @ {label}", True)
        except Exception as exc:
            check(f"tablet tab navigation @ {label}", False, str(exc)[:120])
        more_menu_cycle(page, label)
        check_no_overflow(page, f"final @ {label}")
        page.screenshot(path=f"{SHOTS}/tablet-{label}.png")


def main():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()
        try:
            login(page)
            desktop_phase(page)
            drawer_and_modal_cycle(page)
            mobile_phase(page)
            tablet_phase(page)
        finally:
            try:
                page.screenshot(path=f"{SHOTS}/final-state.png")
            except Exception:
                pass
            context.close()
            browser.close()

    passed = sum(1 for _, ok, _ in RESULTS if ok)
    total = len(RESULTS)
    print("\n" + "=" * 70)
    print(f"RESULT: {passed}/{total} checks passed")
    failures = [(n, e) for n, ok, e in RESULTS if not ok]
    if failures:
        print("\nFAILURES:")
        for name, extra in failures:
            print(f"  - {name}  {extra}")
    print(f"Screenshots: {SHOTS}")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()

