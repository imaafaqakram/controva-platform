#!/usr/bin/env python3
"""Take dashboard screenshots of the running Controva platform."""
import os, time, asyncio
from playwright.async_api import async_playwright

OUT = '/tmp/leadgen-test/screenshots'
os.makedirs(OUT, exist_ok=True)

URL = 'http://127.0.0.1:8080/'
USER = 'admin'
PASS = 'ChangeMe_2026!'

# Each tab in the dashboard sidebar. Map of label -> screenshot filename.
# We click each one and screenshot.
TABS = [
    ('Dashboard',   '01_dashboard.png'),
    ('Search',      '02_search.png'),
    ('Leads',       '03_leads.png'),
    ('Pipeline',    '04_pipeline.png'),
    ('Outreach',    '05_outreach.png'),
    ('Analytics',   '06_analytics.png'),
    ('Intent',      '07_intent.png'),
    ('SEO',         '08_seo.png'),
    ('Competitors', '09_competitors.png'),
    ('People',      '10_people.png'),
    ('Social',      '11_social.png'),
    ('E-commerce',  '12_ecommerce.png'),
    ('Settings',    '13_settings.png'),
]

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            executable_path='/opt/pw-browsers/chromium-1194/chrome-linux/chrome',
            args=['--no-sandbox', '--disable-dev-shm-usage'],
        )
        ctx = await browser.new_context(viewport={'width': 1440, 'height': 900})
        page = await ctx.new_page()

        # ── Login page ────────────────────────────────────────────────
        await page.goto(URL, wait_until='networkidle', timeout=30000)
        await page.wait_for_timeout(1500)  # let React scripts boot
        await page.screenshot(path=f'{OUT}/00_login.png', full_page=True)
        print('saved 00_login.png')

        # The dashboard.html has a login form. Try to fill it.
        try:
            await page.fill('input[type="text"], input[placeholder*="user" i]', USER)
            await page.fill('input[type="password"]', PASS)
            # Try button by text or type=submit
            await page.click('button:has-text("Sign"), button:has-text("Login"), button[type="submit"]')
            await page.wait_for_timeout(2500)
        except Exception as e:
            print(f'login attempt failed: {e}')

        await page.screenshot(path=f'{OUT}/01_dashboard.png', full_page=True)
        print('saved 01_dashboard.png')

        # ── Each sidebar tab ─────────────────────────────────────────
        for label, fname in TABS[1:]:
            try:
                # Find a clickable sidebar element matching the label
                sel = f'button:has-text("{label}"), a:has-text("{label}"), [role="tab"]:has-text("{label}"), li:has-text("{label}")'
                el = page.locator(sel).first
                if await el.count() > 0:
                    await el.click(timeout=5000)
                    await page.wait_for_timeout(1500)
                    await page.screenshot(path=f'{OUT}/{fname}', full_page=True)
                    print(f'saved {fname} ({label})')
                else:
                    print(f'tab not found: {label}')
            except Exception as e:
                print(f'failed {label}: {e}')

        await browser.close()

asyncio.run(main())
