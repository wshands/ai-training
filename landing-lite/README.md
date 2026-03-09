# Landing Lite (Low-Cost Website)

This folder contains a static landing page you can host for free while you recruit design partners.

Files:
- `index.html`
- `styles.css`

## Update links before publishing

In `index.html`, replace any placeholder contact links if needed:
- `admin@aitrainops.com`
- `walt@aitrainops.com`
- `https://www.linkedin.com/in/wshands/`
- `https://github.com/wshands`

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
- Contact buttons currently use `mailto:` and `tel:` links for immediate functionality.
