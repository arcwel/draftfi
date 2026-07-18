#!/usr/bin/env python3
"""Capture README screenshots of the running app at desktop resolution.

Prereqs: the app must be running (FastAPI serving the built frontend), and
Playwright + Chromium installed:

    pip install playwright && python -m playwright install chromium
    python packaging/screenshots.py --url http://127.0.0.1:8020 --out docs/screenshots
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

W, H = 1440, 950


def clip_of(page, locator, pad=0):
    box = locator.bounding_box()
    if not box:
        return None
    return {
        "x": max(box["x"] - pad, 0),
        "y": max(box["y"] - pad, 0),
        "width": box["width"] + pad * 2,
        "height": box["height"] + pad * 2,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8020")
    ap.add_argument("--out", default="docs/screenshots")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_context(
            viewport={"width": W, "height": H}, device_scale_factor=2
        ).new_page()
        page.goto(args.url, wait_until="networkidle")
        page.wait_for_timeout(1200)

        # 1) Hero — the full dashboard on the Base Plan.
        page.screenshot(path=str(out / "01-dashboard.png"))
        print("saved 01-dashboard.png")

        # 2) Budget panel close-up.
        budget = page.get_by_role("heading", name="Monthly Budget").locator(
            "xpath=ancestor::div[contains(@class,'rounded-xl')][1]"
        )
        clip = clip_of(page, budget)
        if clip:
            page.screenshot(path=str(out / "02-budget.png"), clip=clip)
            print("saved 02-budget.png")

        # 3) Ledger close-up.
        ledger = page.get_by_text("Categorization Ledger").locator(
            "xpath=ancestor::div[contains(@class,'border-t')][1]"
        )
        ledger.scroll_into_view_if_needed()
        page.wait_for_timeout(400)
        clip = clip_of(page, ledger)
        if clip:
            page.screenshot(path=str(out / "03-ledger.png"), clip=clip)
            print("saved 03-ledger.png")

        # 4) Compare mode — switch to the sandbox branch and overlay it.
        page.get_by_text("Buy a House 2027").first.click()
        page.wait_for_timeout(600)
        page.get_by_role("checkbox").first.check()
        page.wait_for_timeout(1400)
        page.screenshot(path=str(out / "04-compare-scenario.png"))
        print("saved 04-compare-scenario.png")

        # 5) Runway chart close-up (overlay divergence + safety floor).
        runway = page.get_by_text("Tactical Cash Runway").locator(
            "xpath=ancestor::div[contains(@class,'rounded-xl')][1]"
        )
        runway.scroll_into_view_if_needed()
        page.wait_for_timeout(600)
        clip = clip_of(page, runway)
        if clip:
            page.screenshot(path=str(out / "05-runway-chart.png"), clip=clip)
            print("saved 05-runway-chart.png")

        # 6) Macro wealth chart close-up.
        macro = page.get_by_text("Macro Wealth").locator(
            "xpath=ancestor::div[contains(@class,'rounded-xl')][1]"
        )
        macro.scroll_into_view_if_needed()
        page.wait_for_timeout(600)
        clip = clip_of(page, macro)
        if clip:
            page.screenshot(path=str(out / "06-macro-chart.png"), clip=clip)
            print("saved 06-macro-chart.png")

        browser.close()


if __name__ == "__main__":
    t = time.time()
    main()
    print(f"done in {time.time() - t:.1f}s")
