const { execSync } = require("node:child_process");

const env = { ...process.env };

if (process.env.API_BASE_URL) {
  env.REACT_APP_API_BASE_URL = process.env.API_BASE_URL;
}
if (process.env.WS_BASE_URL) {
  env.REACT_APP_WS_BASE_URL = process.env.WS_BASE_URL;
}
if (process.env.CLERK_PUBLISHABLE_KEY) {
  env.REACT_APP_CLERK_PUBLISHABLE_KEY = process.env.CLERK_PUBLISHABLE_KEY;
}

execSync("npm run deploy", { stdio: "inherit", env });
