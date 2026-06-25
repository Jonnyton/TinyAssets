
# GoDaddy (infra-ops reference)

Drive GoDaddy's web dashboard from the lead agent via the shared CDP Chrome browser. GoDaddy has no first-class API for the products this project uses (domain DNS, Website Builder), so we navigate the admin UI programmatically. All ops run through `scripts/lead_browser.py`.

## Preflight

Every GoDaddy session starts the same way:

```bash
# 1. Confirm user-sim isn't running
python scripts/user_sim_auth_hook.py     # expect 'no-browser' or 'approved'

# 2. Acquire the browser lock (blocks user-sim from claiming the tab)
python scripts/browser_lock.py acquire lead godaddy-<intent>

# 3. Verify lock
python scripts/browser_lock.py status    # shows owner=lead
```

If the lock is already held by user-sim or another lead ops task, wait for release or escalate. **Never** `--force` the lock unless you've verified the prior PID is dead.

## Logging in (first time per Chrome-for-Testing profile)

The `C:\Users\Jonathan\.claude-ai-profile` Chrome-for-Testing profile does NOT share cookies with the host's normal Chrome. First time you navigate to a GoDaddy URL you'll hit `sso.godaddy.com`. Ask the host to log in once in the visible tab; Chrome-for-Testing persists the session for subsequent runs.

## Known URLs

Bookmark in memory — GoDaddy's routing isn't always discoverable from the nav sidebar.

| Purpose | Direct URL |
|---|---|
| Domain portfolio | `https://dcc.godaddy.com/control/portfolio` |
| Specific domain (DNS/settings/privacy) | `https://dcc.godaddy.com/control/dnsmanagement?domainName=<DOMAIN>` |
| All products (Website Builder, email, etc.) | `https://account.godaddy.com/products` |
| Website Builder editor | `https://websites.godaddy.com/en-US/editor/<UUID>/<UUID>/theme` |

The Website Builder publish URL follows the pattern `<slug>.godaddysites.com` and is visible on the products page next to each Websites + Marketing entry.

## Dismissing the tour / promo popups

GoDaddy pops a "Meet your new X 👋 — Take a quick tour" dialog on most pages. Always dismiss before reading content:

```bash
python scripts/lead_browser.py click "button:has-text('Dismiss')"
```

If that selector misses, try `[aria-label='Close']`, `button:has-text('No thanks')`, or `button:has-text('Skip')`.

## DNS management quirk

When a domain's nameservers have been moved to another provider (Cloudflare, Route53, etc.), GoDaddy's DNS page shows:

> **DNS Provider: Cloudflare — This domain's DNS is managed outside GoDaddy**

In that state you CANNOT edit DNS records at GoDaddy; all record changes must happen at the external provider. GoDaddy offers a "revert to default nameservers" link — only use it if you actually want to move DNS back (and break any tunnel/proxy depending on the external provider).

## Beware stale `*.godaddysites.com` free-tier prototypes

**Context (host-verified 2026-04-19):** the host has historical free-tier Website Builder prototypes on `*.godaddysites.com` (e.g., `tinyassets.godaddysites.com`, `tinyassets8.godaddysites.com`). These are OBSOLETE — they predate the paid Websites + Marketing upgrade that's bound directly to the real custom domain (`tinyassets.io`).

**DO NOT** treat `*.godaddysites.com` URLs as the site's publish origin. The real upgraded site publishes straight to the custom domain; there is no intermediate `*.godaddysites.com` slug to CNAME to. The host's products page will list the stale prototypes alongside the real one — the real one is the one whose "live URL" column shows the custom domain (e.g., `tinyassets.io`) rather than a `.godaddysites.com` slug.

Operational rule: when identifying the origin for a custom-domain-bound Website Builder site, navigate to the SPECIFIC site's `Settings → Domain Connection` (or equivalent) rather than guessing from the products list. That panel shows the authoritative A/CNAME records GoDaddy needs for that domain.

## Website Builder origin for custom-domain forwarding

GoDaddy's Websites + Marketing runs on AWS Global Accelerator. When a custom domain's DNS is managed externally (Cloudflare, Route53, etc.), point it at these origin IPs:

- `A` record at apex (`@`) → `76.223.105.230`
- `A` record at apex (`@`) → `13.248.243.5`
- `CNAME` for `www` → the site's `<slug>.godaddysites.com` (the paid upgrade still has one, even though content is the custom-domain version)

**Verified IPs 2026-04-19** via `nslookup *.godaddysites.com`. Both IPs serve all W+M content; GoDaddy routes internally by `Host` header to match the upgraded-site-for-this-custom-domain. So two A records + www CNAME is the complete config.

**Cloudflare proxy setting: OFF (DNS-only).** Website Builder handles its own SSL certificates via ACME; Cloudflare proxy interferes with the cert-provisioning callbacks. Keep the proxy toggle gray, not orange.

**Sanity check after adding records:** `curl -I https://<DOMAIN>/` should return `200` with `Server: DPS/2.0.0+...` (GoDaddy's DPS frontend) within ~5 min of propagation.

## Common ops

### Check which Website Builder site is live for a domain

```bash
python scripts/lead_browser.py goto "https://account.godaddy.com/products"
python scripts/lead_browser.py read --sel "[class*='product' i]"
```

Look for each `<slug>.godaddysites.com` listing. Multiple sites can exist per account — usually only one is the "active" publish target. Confirm by `curl -I https://<slug>.godaddysites.com/` — the active one returns 200 with real content; stale ones may return a placeholder or 404.

### Read current DNS state at GoDaddy (when it IS managing)

```bash
python scripts/lead_browser.py goto "https://dcc.godaddy.com/control/dnsmanagement?domainName=<DOMAIN>"
python scripts/lead_browser.py read
```

## Session end

Always release the lock — even on failure:

```bash
python scripts/browser_lock.py release lead
```

User-sim's auth hook will then return to `approved` and missions can resume.

## Cloudflare DNS dashboard — automation gotchas (learned 2026-04-19)

When adding or editing DNS records via Cloudflare dash automation (same shared CDP browser), the following cost the lead ~15 minutes of wall time on first try. Bake into automation:

- **The "Name" field is a `<textarea name="name">` not `<input>`.** Width renders extremely narrow (~4 px) when collapsed, so `:visible` filters with size thresholds miss it. Correct selector: `textarea[name="name"]`. Target it via `Shift+Tab` from the IPv4 field as a fallback.
- **IPv4 field is `<input name="ipv4_address">`.** This one cooperates with `fill()`.
- **The form's `<label for="name">` points to a `<th id="name">` (table header), NOT the form input.** Don't target by `#name`.
- **Proxy toggle has no good selector.** Not an `input[type=checkbox]`, not a `button[role="switch"]`, no aria-label. Best option: click at bounding-box coords of the visible orange cloud icon in the DNS records table row.
- **`Proxy=ON` breaks GoDaddy W+M origin routing** — Cloudflare terminates SSL on its own cert, GoDaddy W+M origin rejects. Always DNS-only (gray cloud) for records pointing at `76.223.105.230` / `13.248.243.5` / `*.godaddysites.com`.
- **Save button sometimes returns "No success toast" without erroring.** Re-read the page; record may have actually landed. Verify via `nslookup -type=A <domain>` rather than trusting the UI.
- **Moving a Tunnel public-hostname from apex → subdomain deletes the apex CNAME.** Cloudflare auto-managed the record; when the Tunnel's "Published application route" changes hostname, the DNS is updated atomically. Plan the replacement apex record BEFORE making the tunnel change or DNS goes dark.

## Cloudflare Workers dashboard — deploy patterns (learned 2026-04-20)

Landing + route-binding a Cloudflare Worker via the dashboard has two sharp edges that `lead_browser.py`'s default selectors miss.

### Monaco editor — pasting source via clipboard

The Worker code editor is Monaco (VS Code's editor in a web div). `textarea` selectors miss; the editor uses contenteditable divs under a shadow-ish layer. Clipboard paste is faster + more reliable than keystroke typing for any code over ~100 lines.

Pattern (tested on 206-line worker.js, completed in <2s):

```python
# After navigating to .../workers/services/edit/<name>/production
# Focus the editor — multiple selector fallbacks because the
# dashboard iframes/shadow-DOMs the editor unpredictably.
for sel in [".view-lines", ".monaco-editor .view-lines",
            "[class*='editor'] .view-lines", ".monaco-editor"]:
    try:
        page.locator(sel).first.click(timeout=5000)
        break
    except Exception:
        continue
else:
    # Last-ditch: click center of left half of viewport.
    vp = page.viewport_size or {"width": 1280, "height": 800}
    page.mouse.click(vp["width"] // 4, vp["height"] // 2)

# Clear existing + paste via clipboard.
page.keyboard.press("Control+a")
page.keyboard.press("Delete")
page.evaluate(
    "async (t) => { await navigator.clipboard.writeText(t); }",
    file_contents,
)
page.keyboard.press("Control+v")
```

Post-paste verification: `page.locator(".monaco-editor").first.inner_text()` returns the pasted content; grep for a known signature line before clicking Deploy.

### Route binding — Radix UI dropdowns

"Triggers → Domains & Routes → + Add → Route" opens a form with a **Radix UI** zone dropdown that does NOT respond to `lead_browser.py click "text=..."`. The trigger is a `<button aria-haspopup="menu">` inside `form#domains_and_routes_form`; options render with `role="menuitem"`.

Pattern:

```python
# Open the zone dropdown.
trigger = page.locator(
    'form#domains_and_routes_form button[aria-haspopup="menu"]'
).first
trigger.click()
page.wait_for_timeout(800)

# Select the target zone by menuitem text.
for mi in page.locator("[role='menuitem']").all():
    if not mi.is_visible():
        continue
    if "tinyassets.io" in (mi.inner_text(timeout=500) or ""):
        mi.click()
        break

# Verify the trigger now shows the selected zone.
assert trigger.inner_text().strip() == "tinyassets.io"
```

**Gotcha:** clicking the empty "Click to copy" placeholder on the trigger does NOT open the dropdown. Target the button directly by `aria-haspopup="menu"` scoped to the form.

### Route form — pattern field is `<input name="pattern">`

The URL-pattern input (next to the Zone dropdown) has `placeholder="*.example.com/*"`. It DOES respond to `lead_browser.py type 'input[placeholder*="example"]' "tinyassets.io/mcp*"` but the visual render is cramped — the typed value is present in the DOM before it's visible. Verify via `page.locator('input[name="pattern"]').input_value()` rather than trusting the screenshot.

### Clicking "Add route" needs zone committed first

The "Add route" button silently validates on click. If Zone shows "Required" (red underline), the submit no-ops. Always verify `trigger.inner_text()` returns the selected zone name BEFORE clicking Add route.

### Worker deploy flow (condensed, for future ops)

1. `dash.cloudflare.com/<acct>/workers-and-pages` → **Create application** → **Start with Hello World!**
2. Rename placeholder (`nameless-*`) → desired name. Deploy.
3. Navigate `/workers/services/edit/<name>/production` to open Monaco. Clipboard-paste full worker.js. Click **Deploy**.
4. Back to `/triggers` → **Domains & Routes** → **+ Add** → **Route**. Click the Radix zone trigger, pick menuitem. Type route pattern. Click **Add route**.
5. Verify via canary: `python scripts/mcp_public_canary.py --url https://<hostname>/<path> --verbose`.

Total wall time at second-run cadence: ~3 min.

## Known pitfalls

1. **New-tab links.** GoDaddy has "Open in new tab" buttons on several flows. These VIOLATE the one-tab rule and confuse the watchdog. Prefer same-tab navigation (`lead_browser.py goto`). If an in-app link insists on spawning a new tab, navigate directly to the destination URL instead.
2. **iframed editors.** The Website Builder editor lives in a nested iframe; `lead_browser.py read` without `--sel` reads outer shell only. Use `--sel "iframe"` first to locate, then targeted selectors inside.
3. **SSO re-auth every few hours.** GoDaddy expires the SSO session aggressively. If `goto` redirects to `sso.godaddy.com`, host must re-log-in.
4. **Tour popups reappear per product.** Dismiss once per product page; don't assume dismissed globally.
