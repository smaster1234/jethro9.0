#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
EMAIL="${EMAIL:-release-$(date +%s)@example.com}"
PASSWORD="${PASSWORD:-TestPass123!}"
NAME="${NAME:-Release QA}"
FIXTURE_DIR="${FIXTURE_DIR:-backend_lite/fixtures}"
DOC1="${DOC1:-${FIXTURE_DIR}/temporal_01.txt}"
DOC2="${DOC2:-${FIXTURE_DIR}/temporal_02.txt}"

echo "==> הפעלת docker-compose"
docker-compose up -d

echo "==> ממתין לשירות בריאות..."
for _ in {1..30}; do
  if curl -sSf "${BASE_URL}/health" >/dev/null; then
    break
  fi
  sleep 2
done

echo "==> רישום משתמש"
REGISTER_RESP=$(curl -sS -X POST "${BASE_URL}/auth/register" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"${EMAIL}\",\"password\":\"${PASSWORD}\",\"name\":\"${NAME}\"}")

ACCESS_TOKEN=$(echo "${REGISTER_RESP}" | python3 -c 'import json,sys; data=json.load(sys.stdin); print(data.get("access_token",""))')
if [[ -z "${ACCESS_TOKEN}" ]]; then
  echo "==> משתמש קיים, מבצע התחברות"
  LOGIN_RESP=$(curl -sS -X POST "${BASE_URL}/auth/login" \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"${EMAIL}\",\"password\":\"${PASSWORD}\"}")
  ACCESS_TOKEN=$(echo "${LOGIN_RESP}" | python3 -c 'import json,sys; data=json.load(sys.stdin); print(data.get("access_token",""))')
fi

if [[ -z "${ACCESS_TOKEN}" ]]; then
  echo "כשל בקבלת טוקן" >&2
  exit 1
fi

echo "==> יצירת תיק"
CASE_RESP=$(curl -sS -X POST "${BASE_URL}/cases" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"תיק בדיקה - Golden Path\"}")
CASE_ID=$(echo "${CASE_RESP}" | python3 -c 'import json,sys; data=json.load(sys.stdin); print(data.get("id",""))')
if [[ -z "${CASE_ID}" ]]; then
  echo "כשל ביצירת תיק" >&2
  exit 1
fi

echo "==> העלאת מסמכים"
UPLOAD_RESP=$(curl -sS -X POST "${BASE_URL}/api/v1/cases/${CASE_ID}/documents" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -F "file=@${DOC1}" \
  -F "file=@${DOC2}")
DOC_IDS=$(echo "${UPLOAD_RESP}" | python3 -c 'import json,sys; data=json.load(sys.stdin); print(" ".join(data.get("document_ids", [])))')
if [[ -z "${DOC_IDS}" ]]; then
  echo "כשל בהעלאת מסמכים" >&2
  exit 1
fi

echo "==> הרצת ניתוח"
ANALYZE_RESP=$(curl -sS -X POST "${BASE_URL}/api/v1/cases/${CASE_ID}/analyze" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "{}")
JOB_ID=$(echo "${ANALYZE_RESP}" | python3 -c 'import json,sys; data=json.load(sys.stdin); print(data.get("job_id",""))')
if [[ -z "${JOB_ID}" ]]; then
  echo "כשל בהרצת ניתוח" >&2
  exit 1
fi

echo "==> ממתין לסיום הניתוח (${JOB_ID})"
for _ in {1..60}; do
  STATUS_RESP=$(curl -sS "${BASE_URL}/api/v1/jobs/${JOB_ID}" -H "Authorization: Bearer ${ACCESS_TOKEN}")
  STATUS=$(echo "${STATUS_RESP}" | python3 -c 'import json,sys; data=json.load(sys.stdin); print(data.get("status",""))')
  if [[ "${STATUS}" == "done" || "${STATUS}" == "failed" ]]; then
    break
  fi
  sleep 2
done

echo "==> שליפת הרצות"
RUNS_RESP=$(curl -sS "${BASE_URL}/cases/${CASE_ID}/runs" -H "Authorization: Bearer ${ACCESS_TOKEN}")
RUN_ID=$(echo "${RUNS_RESP}" | python3 -c 'import json,sys; data=json.load(sys.stdin); print(data[-1]["id"] if data else "")')
if [[ -z "${RUN_ID}" ]]; then
  echo "לא נמצאה הרצה" >&2
  exit 1
fi

echo "==> יצירת עד וגרסאות"
WITNESS_RESP=$(curl -sS -X POST "${BASE_URL}/api/v1/cases/${CASE_ID}/witnesses" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"name":"עד בדיקה","side":"theirs"}')
WITNESS_ID=$(echo "${WITNESS_RESP}" | python3 -c 'import json,sys; data=json.load(sys.stdin); print(data.get("id",""))')

DOC1_ID=$(echo "${DOC_IDS}" | awk '{print $1}')
DOC2_ID=$(echo "${DOC_IDS}" | awk '{print $2}')

VERSION1_RESP=$(curl -sS -X POST "${BASE_URL}/api/v1/witnesses/${WITNESS_ID}/versions" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "{\"document_id\":\"${DOC1_ID}\",\"version_type\":\"statement\"}")
VERSION1_ID=$(echo "${VERSION1_RESP}" | python3 -c 'import json,sys; data=json.load(sys.stdin); print(data.get("id",""))')
VERSION2_RESP=$(curl -sS -X POST "${BASE_URL}/api/v1/witnesses/${WITNESS_ID}/versions" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "{\"document_id\":\"${DOC2_ID}\",\"version_type\":\"testimony\"}")
VERSION2_ID=$(echo "${VERSION2_RESP}" | python3 -c 'import json,sys; data=json.load(sys.stdin); print(data.get("id",""))')

echo "==> diff לעד"
curl -sS -X POST "${BASE_URL}/api/v1/witnesses/${WITNESS_ID}/versions/diff" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "{\"version_a_id\":\"${VERSION1_ID}\",\"version_b_id\":\"${VERSION2_ID}\"}" >/dev/null || true

echo "==> יצירת תכנית חקירה"
curl -sS -X POST "${BASE_URL}/api/v1/analysis-runs/${RUN_ID}/cross-exam-plan" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "{}" >/dev/null

echo "==> ייצוא DOCX"
curl -sS -o /tmp/cross_exam_plan.docx \
  "${BASE_URL}/api/v1/analysis-runs/${RUN_ID}/export/cross-exam?format=docx" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}"

echo "✅ סיום: /tmp/cross_exam_plan.docx"
