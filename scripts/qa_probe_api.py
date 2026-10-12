import os
import sys
from playwright.sync_api import sync_playwright

BASE = os.environ.get("QA_URL", "http://127.0.0.1:5173")

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page()
    pg.goto(f"{BASE}/login/", wait_until="domcontentloaded")
    pg.fill('input[name="username"]', "admin")
    pg.fill('input[name="password"]', "admin123")
    pg.click('button[type="submit"]')
    pg.wait_for_selector(".plh", timeout=20000)

    def api(path):
        return pg.evaluate(
            "async (u) => { const r = await fetch(u, {credentials:'include'});"
            " return {status: r.status, body: await r.json()}; }", path)

    g = api("/api/guests/")
    guests = g["body"].get("guests", [])
    print(f"guests: status={g['status']} count={len(guests)}")
    if guests:
        import json
        print("FIRST GUIENT KEYS:")
        print(sorted(guests[0].keys()))
        print(json.dumps(guests[0], indent=1)[:1600])
        # find a guest with a room
        withroom = next((x for x in guests if x.get("room")), None)
        if withroom:
            rid = withroom["room"]["id"]
            ph = api(f"/api/room/{rid}/payment-history/")
            print(f"\npayment-history status={ph['status']} keys={sorted(ph['body'].keys())}")
            hist = ph["body"].get("history", [])
            print(f"  history rows={len(hist)}")
            if hist:
                print("  row keys:", sorted(hist[0].keys()))
            eh = api(f"/api/room/{rid}/electricity-history/")
            print(f"\nelectricity-history status={eh['status']} keys={sorted(eh['body'].keys())}")
            ehist = eh["body"].get("history", [])
            print(f"  history rows={len(ehist)}")
            if ehist:
                print("  row keys:", sorted(ehist[0].keys()))
        else:
            print("no guest with a room found")
    b.close()
