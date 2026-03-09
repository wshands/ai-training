# Landing Lite (Low-Cost Website)

This folder contains a static landing page you can host for free while you recruit design partners.

Files:
- `index.html`
- `styles.css`
- `robots.txt`
- `sitemap.xml`
- `og-image.svg`

## Update links before publishing

In `index.html`, replace any placeholder contact links if needed:
- `admin@aitrainops.com`
- `walt@aitrainops.com`
- `https://www.linkedin.com/in/wshands/`
- `https://github.com/wshands`

## Configure lead form (Formspree)

This landing page now includes an in-page pilot request form with a thank-you state.

Before publishing:
1. Create a form at Formspree and copy your endpoint, e.g. `https://formspree.io/f/abcdwxyz`.
2. In `index.html`, replace:
   - `action="https://formspree.io/f/your-form-id"`
   with your real endpoint.
3. Keep `_next` hidden field as-is. It redirects back to the same page with `?submitted=1#pilot-form` and shows a thank-you message.

Fallback behavior:
- If the Formspree endpoint is not configured, the form blocks submit and shows a visible config warning.
- Visitors can still email directly via the fallback `admin@aitrainops.com` link.

## Quick local preview

From this folder:

```bash
python3 -m http.server 8080
```

Then open `http://localhost:8080`.

## Free hosting options

## Cloudflare Pages (recommended)
1. Push this repo to GitHub.
2. In Cloudflare Pages, create a new project and connect the repo.
3. Build settings:
   - Framework preset: `None`
   - Build command: *(empty)*
   - Build output directory: `landing-lite`
4. Add custom domain:
   - easiest: `www.aitrainops.com`
   - apex domain setup may require nameserver move to Cloudflare.

## Netlify
1. New site from Git.
2. Build command: *(empty)*
3. Publish directory: `landing-lite`
4. Add custom domain and enable HTTPS.

## Notes
- This is static HTML/CSS, so no backend or AWS runtime costs.
- Includes a no-backend form flow plus `mailto:` fallback for contact.
- SEO files included: canonical, Open Graph/Twitter tags, JSON-LD, `robots.txt`, and `sitemap.xml`.
