#!/bin/sh
set -e

API_URL="${API_URL:-${VITE_API_URL:-}}"
export API_URL

echo "Writing /app/dist/env.js with API_URL=${API_URL:-<empty>}"
if ! node -e 'const fs=require("fs"); const api=process.env.API_URL || ""; const payload={API_URL: api}; fs.writeFileSync("/app/dist/env.js","window.__JETHRO_ENV__ = " + JSON.stringify(payload) + ";\n");'; then
  echo "WARN: failed to write /app/dist/env.js, continuing"
fi

echo "Starting static server on port ${PORT:-3000}"
exec serve dist -s -l "${PORT:-3000}"
