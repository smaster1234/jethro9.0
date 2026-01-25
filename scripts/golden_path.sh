#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
EMAIL="${EMAIL:-release-$(date +%s)@example.com}"
PASSWORD="${PASSWORD:-TestPass123!}"
NAME="${NAME:-Release QA}"
FIXTURE_DIR="${FIXTURE_DIR:-backend_lite/fixtures}"
DOC1="${DOC1:-${FIXTURE_DIR}/temporal_01.txt}"
DOC2="${DOC2:-${FIXTURE_DIR}/temporal_02.txt}"
DOC_TEXT_1="${DOC_TEXT_1:-On 2020-01-01 the contract was signed. The witness was present.}"
DOC_TEXT_2="${DOC_TEXT_2:-On 2020-02-01 the contract was signed. The witness was not present.}"

COMPOSE_CMD=""
if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  COMPOSE_CMD="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE_CMD="docker-compose"
else
  echo "Docker Compose לא נמצא (נדרש docker compose או docker-compose)" >&2
  exit 1
fi

ensure_fixture() {
  local path="$1"
  local text="$2"
  if [[ -f "$path" ]]; then
    return 0
  fi
  mkdir -p "$(dirname "$path")"
  local ext="${path##*.}"
  if [[ "$ext" == "pdf" ]]; then
    python3 - "$path" "$text" <<'PY'
import sys
from pathlib import Path

def esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

path = Path(sys.argv[1])
text = esc(sys.argv[2])
content = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET"
objects = []
objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
objects.append(b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>")
objects.append(b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>")
objects.append(f"<< /Length {len(content)} >>\\nstream\\n{content}\\nendstream".encode("utf-8"))
objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

pdf = bytearray()
pdf.extend(b"%PDF-1.4\\n")
offsets = [0]
for i, obj in enumerate(objects, start=1):
    offsets.append(len(pdf))
    pdf.extend(f"{i} 0 obj\\n".encode("utf-8"))
    pdf.extend(obj)
    pdf.extend(b"\\nendobj\\n")

xref_pos = len(pdf)
pdf.extend(b"xref\\n0 6\\n0000000000 65535 f \\n")
for off in offsets[1:]:
    pdf.extend(f"{off:010d} 00000 n \\n".encode("utf-8"))
pdf.extend(b"trailer\\n<< /Size 6 /Root 1 0 R >>\\nstartxref\\n")
pdf.extend(f"{xref_pos}\\n%%EOF".encode("utf-8"))

path.write_bytes(pdf)
PY
    return 0
  fi
  if [[ "$ext" == "docx" ]]; then
    python3 - "$path" "$text" <<'PY'
import sys
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

path = Path(sys.argv[1])
text = sys.argv[2]
paragraphs = [p for p in text.split("\\n") if p]

body_parts = []
for para in paragraphs:
    body_parts.append(f"<w:p><w:r><w:t>{escape(para)}</w:t></w:r></w:p>")
body = "".join(body_parts)

doc_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    {body}
    <w:sectPr>
      <w:pgSz w:w="11906" w:h="16838"/>
      <w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/>
    </w:sectPr>
  </w:body>
</w:document>
"""

content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>
"""

rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>
"""

with zipfile.ZipFile(path, "w") as zf:
    zf.writestr("[Content_Types].xml", content_types)
    zf.writestr("_rels/.rels", rels)
    zf.writestr("word/document.xml", doc_xml)
PY
    return 0
  fi
}

doc_text_for_path() {
  local path="$1"
  if [[ "$path" == *"02"* ]]; then
    echo "${DOC_TEXT_2}"
  else
    echo "${DOC_TEXT_1}"
  fi
}

ensure_fixture "${DOC1}" "$(doc_text_for_path "${DOC1}")"
ensure_fixture "${DOC2}" "$(doc_text_for_path "${DOC2}")"

echo "==> הפעלת ${COMPOSE_CMD}"
${COMPOSE_CMD} up -d

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

echo "==> אימון (Training) - התחלה"
PLAN_RESP=$(curl -sS "${BASE_URL}/api/v1/analysis-runs/${RUN_ID}/cross-exam-plan" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}")
PLAN_ID=$(echo "${PLAN_RESP}" | python3 -c 'import json,sys; data=json.load(sys.stdin); print(data.get("plan_id",""))')
PLAN_WITNESS_ID=$(echo "${PLAN_RESP}" | python3 -c 'import json,sys; data=json.load(sys.stdin); print(data.get("witness_id",""))')
if [[ -n "${PLAN_ID}" && -n "${PLAN_WITNESS_ID}" ]]; then
  TRAINING_RESP=$(curl -sS -X POST "${BASE_URL}/api/v1/cases/${CASE_ID}/training/start" \
    -H "Authorization: Bearer ${ACCESS_TOKEN}" \
    -H "Content-Type: application/json" \
    -d "{\"plan_id\":\"${PLAN_ID}\",\"witness_id\":\"${PLAN_WITNESS_ID}\",\"persona\":\"cooperative\"}")
  TRAINING_ID=$(echo "${TRAINING_RESP}" | python3 -c 'import json,sys; data=json.load(sys.stdin); print(data.get("session_id",""))')
  if [[ -z "${TRAINING_ID}" ]]; then
    echo "אזהרה: לא נוצר אימון" >&2
  fi
else
  echo "אזהרה: אין תכנית/עד לאימון" >&2
fi

echo "==> בדיקת עוגנים (Resolve Anchor)"
RUN_DETAIL=$(curl -sS "${BASE_URL}/api/v1/analysis-runs/${RUN_ID}" -H "Authorization: Bearer ${ACCESS_TOKEN}")
ANCHOR=$(echo "${RUN_DETAIL}" | python3 -c 'import json,sys; data=json.load(sys.stdin); c=data.get("contradictions",[]); anchor=None; \
print((c[0].get("claim1_locator") or c[0].get("claim2_locator") or {}).get("doc_id","") if c else "")')
if [[ -n "${ANCHOR}" ]]; then
  ANCHOR_PAYLOAD=$(echo "${RUN_DETAIL}" | python3 -c 'import json,sys; data=json.load(sys.stdin); c=data.get("contradictions",[]); \
anchor=(c[0].get("claim1_locator") or c[0].get("claim2_locator") or {}) if c else {}; print(json.dumps({"anchor": anchor, "context": 1}))')
  curl -sS -X POST "${BASE_URL}/api/v1/anchors/resolve" \
    -H "Authorization: Bearer ${ACCESS_TOKEN}" \
    -H "Content-Type: application/json" \
    -d "${ANCHOR_PAYLOAD}" >/dev/null || true
else
  echo "אזהרה: לא נמצא עוגן לבדיקה" >&2
fi

echo "==> ייצוא DOCX"
curl -sS -o /tmp/cross_exam_plan.docx \
  "${BASE_URL}/api/v1/analysis-runs/${RUN_ID}/export/cross-exam?format=docx" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}"

echo "✅ סיום: /tmp/cross_exam_plan.docx"
