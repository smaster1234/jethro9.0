#!/bin/sh
set -eu

API_URL="${API_URL:-${VITE_API_URL:-}}"
export API_URL

node -e 'const fs=require("fs"); const api=process.env.API_URL || ""; const payload={API_URL: api}; fs.writeFileSync("/app/dist/env.js","window.__JETHRO_ENV__ = " + JSON.stringify(payload) + ";\n");'

exec serve dist -s -l "${PORT:-3000}"
