#!/usr/bin/env python3
"""Focused repro: open RECORD EXPENSE modal and capture console/page errors."""
import sys
sys.path.insert(0, "/Users/ayush/Downloads/Hotel_rental-main 5/scripts")
from qa_nav_browser import login  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

with sync_playwright() as pw:
    b = pw.chromium.launch(headless=True)
    ctx = b.new_context(viewport={"width": 1280, "height": 800})
    page = ctx.new_page()
    page.on("console", lambda m: print(f"CONSOLE[{m.type}] {m.text[:300]}"))
    page.on("pageerror", lambda e: print(f"PAGEERROR {str(e)[:500]}"))
    login(page)
    page.locator(".top-nav .nav-link", has_text="Expenses").first.click()
    page.wait_for_selector("button:has-text('RECORD EXPENSE')", timeout=8000)
    print("button found")
    page.click("button:has-text('RECORD EXPENSE')")
    print("clicked, url:", page.url)
    try:
        page.wait_for_selector(".modal-overlay", timeout=4000)
        print("modal-overlay PRESENT")
        print("visible:", page.locator(".modal-overlay .modal-box").is_visible())
        page.wait_for_timeout(400)  # let backdrop-in (both fill) settle
        st = page.evaluate("""() => {
            const o = document.querySelector('.modal-overlay');
            const box = document.querySelector('.modal-box');
            const cs = o && getComputedStyle(o);
            return {overlay: !!o, box: !!box,
                    display: cs && cs.display, vis: cs && cs.visibility,
                    opacity: cs && cs.opacity, z: cs && cs.zIndex,
                    rect: o && JSON.stringify(o.getBoundingClientRect()),
                    bodyOverflow: document.body.style.overflow};
        }""")
        print("state:", st)
    except Exception as exc:
        print("MODAL NOT FOUND:", str(exc)[:300])
        print("overlay count:", page.locator(".modal-overlay").count())
        print("expense form visible:", page.locator("button:has-text('RECORD EXPENSE')").count())
    page.screenshot(path="/tmp/nav-qa/repro-modal.png")
    # Is navigation blocked behind an invisible overlay?
    blocked = page.evaluate("""() => {
        const el = document.querySelector('.top-nav .nav-link');
        if (!el) return 'no nav';
        const r = el.getBoundingClientRect();
        const hit = document.elementFromPoint(r.left + r.width/2, r.top + r.height/2);
        return hit && (el === hit || el.contains(hit)) ? 'ok'
            : 'blocked by ' + (hit && (hit.className || hit.tagName));
    }""")
    print("nav hit-test:", blocked)
    ctx.close()
    b.close()
