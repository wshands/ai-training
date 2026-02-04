Create React App env files are read at build/start time, and only variables
prefixed with REACT_APP_ are embedded into the bundle.

Order (highest precedence wins) for production build (npm run build):

.env
.env.local
.env.production
.env.production.local ← overrides everything above

For development (npm start):

.env
.env.local
.env.development
.env.development.local

RE: REACT_APP_CLERK_PUBLISHABLE_KEY=pk_test... or REACT_APP_CLERK_PUBLISHABLE_KEY=pk_live... While it’s “publishable” (safe to expose in the browser), it still ties to your production Clerk instance, so best practice is to keep it out of the repo and inject it at build time.

Put defaults in .env.development and .env.production.
Put overrides/secrets in .env.development.local / .env.production.local.
So keep:
REACT_APP_API_BASE_URL / REACT_APP_WS_BASE_URL in .env.development and .env.production
Only REACT_APP_CLERK_PUBLISHABLE_KEY (and any overrides) in the *.local files