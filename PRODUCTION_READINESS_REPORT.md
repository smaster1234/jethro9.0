# JETHRO 9.0 — דוח מוכנות לפרודקשן
### סקירה מקיפה: איכות ניתוח, אבטחה, מניעת שימוש לא הוגן, קרדיטים, ממשק אדמין
**תאריך:** 31 ינואר 2026
**גרסה:** 9.0
**סביבה:** Railway (single-container)

---

## תוכן עניינים

1. [סיכום מנהלים](#סיכום-מנהלים)
2. [איכות הניתוחים — מצב נוכחי ופערים](#1-איכות-הניתוחים)
3. [אבטחה — ביקורת מלאה](#2-אבטחה)
4. [מניעת שימוש לא הוגן ו-Rate Limiting](#3-מניעת-שימוש-לא-הוגן)
5. [מעקב קרדיטים והצגה למשתמש](#4-קרדיטים-ומעקב-שימוש)
6. [ממשק אדמין — מצב נוכחי וצרכים](#5-ממשק-אדמין)
7. [תוכנית פיתוח המשך — שלבים](#6-תוכנית-פיתוח)

---

## סיכום מנהלים

### מה עובד
- Pipeline ניתוח פעיל: חילוץ טענות → זיהוי rule-based → אימות LLM (Gemini)
- אימות JWT + RBAC עם 4 רמות הרשאה
- סכמת קרדיטים קיימת ב-DB (CreditLedger + UserCreditBalance)
- Rate limiting קיים (Redis-based) — אך **מכובה** כברירת מחדל
- Security headers + CORS מוגדרים
- Frontend פונקציונלי עם notebook UI

### מה חסר (קריטי)
| פער | חומרה | השפעה |
|-----|--------|--------|
| קרדיטים לא נגבים בפועל | 🔴 קריטי | שימוש ללא הגבלה ב-LLM API |
| Rate limiting מכובה | 🔴 קריטי | אין הגנה מפני abuse |
| `/analyze` ציבורי ללא auth | 🔴 קריטי | כל אחד יכול להריץ ניתוחים |
| אין ממשק אדמין | 🔴 קריטי | אין פיקוח על המערכת |
| אין תצוגת קרדיטים למשתמש | 🟡 גבוה | אין שקיפות שימוש |
| Verifier prompt חסר דוגמאות | 🟡 גבוה | דיוק נמוך בזיהוי סתירות |

---

## 1. איכות הניתוחים

### 1.1 זרימת הניתוח הנוכחית

```
מסמכים → חילוץ טענות → זיהוי rule-based → אימות Gemini Flash → שמירה ל-DB
                                    ↓
                             155 מועמדים
                                    ↓
                        Gemini 2.0 Flash (30 קריאות)
                                    ↓
                    confirmed / rejected / new (לא נבדק)
```

### 1.2 חילוץ טענות (extractor.py)

| בעיה | חומרה | תיאור |
|------|--------|--------|
| פיצול משפטים אגרסיבי | גבוה | נקודות בתוך ציטוטים/מספרי תיק שוברות את הטענה |
| אין מודעות לסוגריים/מרכאות | גבוה | `"טענה א (ראו סעיף 5. לעיל)"` נחתכת באמצע |
| מיקום טענות שביר | בינוני | `find()` על טקסט מנורמל נכשל אם הנורמליזציה שינתה תווים |
| ציון אמון גנרי | בינוני | 0.8-1.0 hardcoded, לא משקף איכות חילוץ |

**המלצה:** פיצול sentence-aware שמכבד מרכאות, סוגריים, ומספרי תיק.

### 1.3 זיהוי Rule-Based (detector.py)

| בעיה | חומרה | תיאור |
|------|--------|--------|
| סף סכומים קבוע 10% | גבוה | ₪5,000 מול ₪5,050 = לא סתירה. ₪1M מול ₪900K = סתירה. סף לא אדפטיבי |
| השוואת תאריכים חלקית | גבוה | "2024" מול "15.3.2024" = תאריכים שונים (false positive) |
| relatedness = word overlap בלבד | גבוה | שתי טענות על אותו אירוע עם מילים שונות = relatedness נמוך |
| מספרי תיק כתאריכים | בינוני | `17682-06-25` עלול להיחשב כתאריך |

**המלצה:**
```
סף אדפטיבי: threshold = max(0.01, 0.1 / (max_amount / 1000))
תאריכים: השוואה רק ברמת granularity זהה
relatedness: שקלול entity overlap + word overlap
```

### 1.4 Reconciler (reconciler.py)

| בעיה | חומרה | תיאור |
|------|--------|--------|
| entity matching עם SequenceMatcher | גבוה | "בנק לאומי בע״מ" מול "הבנק הלאומי" = similarity 0.6 (לא מתאים) |
| שער incompleteness חוסם | בינוני | speaker_mode חסר → INSUFFICIENT_CONTEXT גם כשיש negation ברור |
| scope comparison מחרוזתי | בינוני | `"all"` מול `"allClaims"` = לא תואם |

**המלצה:** מילון כינויים משפטי, token-based similarity, שער incompleteness מרוכך.

### 1.5 Verifier Prompt (verifier.py) — Gemini 2.0 Flash

| בעיה | חומרה | תיאור |
|------|--------|--------|
| אין few-shot examples | גבוה | המודל מנחש 9 קטגוריות בלי דוגמה אחת |
| גבולות קטגוריות לא ברורים | גבוה | מתי DISAGREEMENT ומתי ROLE_MISMATCH? |
| suggested_type מטה את המודל | בינוני | verifier נוטה לאשר את סוג הסתירה שקיבל |
| אין הקשר משפטי ישראלי | בינוני | לא מוזכרים: ממצא בימ״ש מול טענת צד, עדות מול חוו״ד |

**המלצה:** להוסיף 5-10 דוגמאות קונקרטיות בעברית לפרומפט, עם מקרי קצה.

### 1.6 Claim Enricher (claim_enricher.py)

| בעיה | חומרה | תיאור |
|------|--------|--------|
| speaker mode = first match | גבוה | "בקביעתו, הנתבע טען" → PARTY_CLAIM במקום FINDING |
| plane לא קשור ל-speaker mode | בינוני | (OPINION mode, FACT plane) = חוסר עקביות |
| negation בינארי בלי scope | בינוני | "לא חתם אבל שלח" = negated (שגוי, חלקי) |

**המלצה:** ספציפיות → עדיפות. FINDING > QUOTE > PARTY_CLAIM > OPINION.

### 1.7 ציון איכות כולל

| רכיב | ציון | הערה |
|-------|------|------|
| חילוץ טענות | 7/10 | פיצול משפטים בעייתי |
| זיהוי rule-based | 6/10 | סיפים קבועים, relatedness חלש |
| Reconciler | 7/10 | entity matching חלש לעברית |
| Verifier prompt | 6/10 | חסר דוגמאות ו-few-shot |
| Dedup | 7/10 | char-level, לא סמנטי |
| Enricher | 6/10 | speaker mode ו-scope בעייתיים |
| Insights | 7/10 | נוסחת risk שגויה, תבניות גנריות |
| **ממוצע** | **6.6/10** | **צריך שיפור לפרודקשן** |

---

## 2. אבטחה

### 2.1 מצב נוכחי — מה קיים

| רכיב | מצב | פרטים |
|-------|------|--------|
| JWT Auth | ✅ טוב | HS256, access 60min, refresh 7 ימים |
| Password hashing | ✅ טוב | bcrypt via passlib |
| RBAC | ✅ טוב | 4 רמות: super_admin, admin, member, viewer |
| SQL Injection | ✅ מוגן | SQLAlchemy ORM, פרמטרים מוצמדים |
| Security headers | ✅ טוב | HSTS, X-Frame-Options, nosniff |
| File upload validation | ✅ חלקי | MIME check + size limit 25MB |
| API keys in env | ✅ טוב | לא hardcoded בקוד |

### 2.2 פערי אבטחה קריטיים

#### 🔴 CRITICAL — JWT Secret ברירת מחדל
```python
JWT_SECRET_KEY = _jwt_secret_raw or "dev-secret-key-DO-NOT-USE-IN-PRODUCTION"
```
**אם לא הוגדר בסביבה** → כל token ניתן לזיוף.

**תיקון:** קריסה מיידית בפרודקשן אם `JWT_SECRET_KEY` לא מוגדר.

#### 🔴 CRITICAL — `/analyze` ציבורי
```python
@app.post("/api/v1/analyze")
async def analyze_text(request: AnalyzeTextRequest):
    # אין auth check!
```
**כל אחד** יכול לשלוח טקסט ולהפעיל קריאות LLM.

**תיקון:** `auth: AuthContext = Depends(get_auth_context)`.

#### 🔴 CRITICAL — `/debug/init-demo` ציבורי
```python
@app.post("/debug/init-demo")
async def init_demo_users(db: Session = Depends(get_db)):
    # אין auth check! יוצר משתמשי דמו
```
**תיקון:** לחסום בפרודקשן או לדרוש super_admin.

#### 🟡 HIGH — CORS headers פתוח מדי
```python
allow_headers=["*"]  # מאפשר כל header כולל X-User-Id
```
**תיקון:** רשימה מפורשת: `["content-type", "authorization"]`.

#### 🟡 HIGH — Logout לא מבטל token
- Token blacklist קיים ב-DB אבל **לא נבדק** בכל בקשה
- אחרי logout, ה-token הישן עדיין עובד

**תיקון:** בדיקת blacklist ב-`get_auth_context()`.

#### 🟡 HIGH — CSP עם unsafe-eval
```python
script-src 'self' 'unsafe-inline' 'unsafe-eval'
```
**תיקון:** הסרה בפרודקשן, שימוש ב-nonce.

### 2.3 סיכום אבטחה — טבלת סיכון

```
🔴 קריטי (תקן מיד):
   ├── JWT Secret default
   ├── /analyze ללא auth
   └── /debug endpoints ציבוריים

🟡 גבוה (תקן לפני production):
   ├── CORS allow_headers=*
   ├── Logout לא מבטל token
   ├── CSP unsafe-eval
   └── אין הגבלת אורך טקסט ב-/analyze

🔵 בינוני (תקן בשלב הבא):
   ├── אין audit log
   ├── אין structured logging
   ├── אין password complexity
   └── אין IP-based rate limiting
```

---

## 3. מניעת שימוש לא הוגן

### 3.1 Rate Limiting — מצב נוכחי

```
מימוש: ✅ קיים (Redis sliding window)
מופעל: ❌ מכובה כברירת מחדל

סיפים:
  - per user:  30 req/min
  - per firm:  200 req/min
  - /analyze:  5 req/min
  - docs/day:  1,000 per firm
  - OCR/day:   5,000 pages per firm

בעיה: RATE_LIMIT_ENABLED=false (ברירת מחדל!)
```

### 3.2 תרחיש abuse

```
ללא rate limiting + ללא auth + ללא קרדיטים:

  תוקף שולח 1,000 בקשות /analyze
  × 30 קריאות verifier לכל אחת
  = 30,000 קריאות Gemini API
  = ~$30 בעלויות API
  = 0 קרדיטים שנגבו

  ← זה אפשרי כרגע!
```

### 3.3 מה צריך לתקן (סדר עדיפויות)

1. **הפעל rate limiting** — `RATE_LIMIT_ENABLED=true`
2. **דרוש auth** על `/analyze` ו-`/analyze_text`
3. **הפעל גביית קרדיטים** (סכמת DB קיימת, אין קוד גבייה)
4. **הגבל אורך טקסט** — max 100KB ב-`/analyze`
5. **Rate limit ברמת IP** כשכבה שנייה

---

## 4. קרדיטים ומעקב שימוש

### 4.1 מצב נוכחי

```
DB Schema: ✅ קיים
  - CreditLedger (היסטוריית עסקאות)
  - UserCreditBalance (יתרה נוכחית)
  - Transaction types: grant, analysis, verification, refund, adjustment

קוד גבייה: ❌ לא קיים
UI להצגה: ❌ לא קיים
Admin UI: ❌ לא קיים
```

### 4.2 מה חסר — תשתית גבייה

#### Backend

```python
# צריך להוסיף ב-api_upload.py לפני כל ניתוח:

async def analyze_case(...):
    # 1. בדיקת יתרה
    balance = get_user_credit_balance(auth.user_id, db)
    estimated_cost = estimate_analysis_cost(document_count)
    if balance < estimated_cost:
        raise HTTPException(402, "אין מספיק קרדיטים לניתוח")

    # 2. הקפאת קרדיטים
    reservation = reserve_credits(auth.user_id, estimated_cost)

    # 3. הרצת ניתוח
    result = await task_analyze_case(...)

    # 4. גבייה לפי צריכה בפועל
    actual_cost = calculate_actual_cost(result)
    finalize_credits(reservation, actual_cost)
```

#### Frontend — תצוגת קרדיטים

```
צריך להוסיף:
  - תצוגת יתרה בסרגל העליון (כמו "47 קרדיטים נותרו")
  - עמוד /billing עם:
    - יתרה נוכחית
    - היסטוריית שימוש (טבלה)
    - עלות לכל ניתוח
    - תרשים שימוש חודשי
  - אזהרה לפני ניתוח עם אומדן עלות
  - חסימה כשהיתרה נגמרת
```

### 4.3 מודל תמחור מוצע

| פעולה | עלות קרדיטים | עלות API בפועל |
|-------|--------------|----------------|
| העלאת מסמך | 1 | ~$0.001 |
| ניתוח (per claim) | 0.5 | ~$0.002 |
| אימות (per candidate) | 2 | ~$0.01 |
| OCR (per page) | 1 | ~$0.005 |
| **ניתוח טיפוסי** (50 טענות, 15 אימותים) | **~55 קרדיטים** | **~$0.25** |

---

## 5. ממשק אדמין

### 5.1 מצב נוכחי

```
קיים:
  ✅ ניהול משתמשים בסיסי (/users)
  ✅ ניהול צוותים (/teams)
  ✅ הגדרות (/settings)
  ✅ Dashboard בסיסי (/dashboard)

חסר:
  ❌ Admin dashboard מרכזי
  ❌ מעקב שימוש LLM
  ❌ ניהול קרדיטים
  ❌ Audit log
  ❌ ניטור ביצועים
  ❌ ניהול מודלים/הגדרות מערכת
```

### 5.2 ממשק אדמין מוצע — ארכיטקטורה

```
/admin
├── /admin/dashboard
│   ├── סטטיסטיקות כלליות (תיקים, מסמכים, ניתוחים, משתמשים)
│   ├── עלויות LLM (היום / שבוע / חודש)
│   ├── שיעור אימות (verified / rejected / total)
│   └── התראות מערכת
│
├── /admin/users
│   ├── רשימת כל המשתמשים (חיפוש, סינון)
│   ├── עריכת role / הקפאת חשבון
│   ├── היסטוריית כניסה
│   └── שימוש per-user
│
├── /admin/firms
│   ├── רשימת ארגונים
│   ├── מכסות ותקציב per-firm
│   ├── שימוש מצטבר
│   └── חיוב חודשי
│
├── /admin/billing
│   ├── יתרות קרדיטים (per user + per firm)
│   ├── היסטוריית עסקאות
│   ├── הוספת/הפחתת קרדיטים ידנית
│   └── ניהול subscription plans
│
├── /admin/analytics
│   ├── שימוש ב-LLM: קריאות, tokens, עלות
│   ├── ניתוחים per-day (תרשים)
│   ├── דיוק verifier (confirmed/rejected ratio)
│   └── שגיאות API (rate, type)
│
├── /admin/models
│   ├── מודל analyzer נוכחי + החלפה
│   ├── מודל verifier נוכחי + החלפה
│   ├── verifier max_calls
│   ├── סיפים ופרמטרים
│   └── A/B testing הגדרות
│
├── /admin/audit
│   ├── לוג פעולות (CRUD, login, analyze)
│   ├── סינון לפי user / action / time
│   └── export ל-CSV
│
└── /admin/system
    ├── Health check (DB, Redis, LLM APIs)
    ├── משתני סביבה (read-only, ללא secrets)
    ├── Feature flags
    └── Rate limit הגדרות
```

### 5.3 Endpoints נדרשים (Backend)

```
GET    /api/v1/admin/dashboard          # סטטיסטיקות כלליות
GET    /api/v1/admin/users              # רשימת כל המשתמשים
PUT    /api/v1/admin/users/:id/role     # עדכון role
POST   /api/v1/admin/users/:id/suspend  # הקפאה/ביטול
GET    /api/v1/admin/firms              # רשימת ארגונים
GET    /api/v1/admin/firms/:id/usage    # שימוש per-firm
GET    /api/v1/admin/billing/ledger     # היסטוריית קרדיטים
POST   /api/v1/admin/billing/grant      # הענקת קרדיטים
POST   /api/v1/admin/billing/adjust     # התאמה ידנית
GET    /api/v1/admin/analytics/llm      # שימוש LLM
GET    /api/v1/admin/analytics/accuracy # דיוק verifier
GET    /api/v1/admin/audit/logs         # audit trail
PUT    /api/v1/admin/models/config      # עדכון model config
GET    /api/v1/admin/system/health      # בריאות מערכת
```

---

## 6. תוכנית פיתוח — שלבים לפרודקשן

### Phase 0: תיקונים קריטיים (חובה לפני פרודקשן)

**אבטחה:**
- [ ] `RATE_LIMIT_ENABLED=true` כברירת מחדל
- [ ] דרישת auth על `/analyze`, `/analyze_text`
- [ ] חסימת `/debug/*` בפרודקשן
- [ ] קריסה אם `JWT_SECRET_KEY` לא מוגדר
- [ ] CORS: `allow_headers` מפורש (לא `*`)
- [ ] הגבלת אורך טקסט ב-`/analyze` (100KB)

**קרדיטים:**
- [ ] `check_credit_balance()` לפני כל ניתוח
- [ ] `deduct_credits()` אחרי ניתוח
- [ ] Endpoint: `GET /api/v1/me/credits`
- [ ] תצוגת יתרה ב-frontend header

**איכות:**
- [ ] 5 דוגמאות few-shot ב-verifier prompt
- [ ] סף סכומים אדפטיבי ב-detector

### Phase 1: ממשק אדמין בסיסי

**Backend:**
- [ ] `/admin/dashboard` — סטטיסטיקות
- [ ] `/admin/users` — ניהול משתמשים + roles
- [ ] `/admin/billing/ledger` — צפייה בקרדיטים
- [ ] `/admin/billing/grant` — הענקת קרדיטים
- [ ] Audit log table + logging middleware

**Frontend:**
- [ ] Admin layout עם sidebar ייעודי
- [ ] Dashboard עם כרטיסיות סטטיסטיקה
- [ ] טבלת משתמשים עם פעולות
- [ ] עמוד billing עם היסטוריה

### Phase 2: שיפור איכות ניתוח

**Prompts:**
- [ ] 10 דוגמאות few-shot בעברית (5 true, 5 false positive)
- [ ] הגדרת גבולות ברורים בין 9 קטגוריות
- [ ] הקשר משפטי ישראלי (ממצא מול טענה, עד מול בעל דין)
- [ ] ביטול `suggested_type` מהפרומפט (מניעת הטיה)

**Detection:**
- [ ] Relatedness: entity overlap + word overlap (משוקלל)
- [ ] תאריכים: granularity-aware comparison
- [ ] Entity matching: token-based + מילון כינויים
- [ ] Speaker mode: ranking by specificity

**Pipeline:**
- [ ] Confidence מופרד: detection / reconciliation / verifier
- [ ] Enrichment חובה (לא optional)
- [ ] Dedup אחרי reconciliation
- [ ] Category → insights weighting

### Phase 3: Analytics ו-Learning

**Analytics:**
- [ ] `/admin/analytics/llm` — עלויות, קריאות, tokens
- [ ] `/admin/analytics/accuracy` — precision/recall per type
- [ ] תרשים שימוש יומי
- [ ] דוח חודשי לכל firm

**Learning system:**
- [ ] Few-shot examples אוטומטיים מפידבק משתמשים
- [ ] Confidence calibration per type
- [ ] A/B testing למודלים שונים
- [ ] Ground truth test suite (50+ מקרי בדיקה)

### Phase 4: Production hardening

**Monitoring:**
- [ ] Structured JSON logging
- [ ] Request/response logging middleware
- [ ] Error alerting (PagerDuty / Slack)
- [ ] Health check: DB + Redis + LLM APIs

**Resilience:**
- [ ] Circuit breaker for LLM APIs
- [ ] Graceful degradation (verifier fails → rule-based only)
- [ ] Database connection pooling
- [ ] Background job queue (for large cases)

**Compliance:**
- [ ] Audit trail מלא
- [ ] Data retention policy
- [ ] GDPR: right to delete
- [ ] תנאי שימוש + מדיניות פרטיות

---

## נספח א: משתני סביבה נדרשים לפרודקשן

```bash
# Authentication (חובה)
JWT_SECRET_KEY=<random-string-32-chars-minimum>
ENVIRONMENT=production

# LLM (חובה)
LLM_MODE=gemini
GEMINI_API_KEY=<your-gemini-api-key>
# אופציונלי:
# GEMINI_ANALYZER_MODEL=gemini-2.5-pro-preview-03-25
# GEMINI_VERIFIER_MODEL=gemini-2.0-flash-001
# VERIFIER_MAX_CALLS=30

# Rate Limiting (חובה)
RATE_LIMIT_ENABLED=true
REDIS_URL=<redis-connection-string>
# אופציונלי:
# RATE_LIMIT_PER_USER=30
# RATE_LIMIT_PER_FIRM=200
# RATE_LIMIT_ANALYZE=5

# Storage
S3_BUCKET=<bucket-name>
S3_ACCESS_KEY=<key>
S3_SECRET_KEY=<key>
S3_ENDPOINT_URL=<url>

# Database
DATABASE_URL=<postgres-connection-string>

# CORS (חובה)
CORS_ALLOW_ORIGINS=https://your-domain.com

# Security
ENFORCE_HTTPS=true
```

## נספח ב: סיכון עלויות LLM

| תרחיש | קריאות Gemini/חודש | עלות משוערת |
|--------|---------------------|-------------|
| 10 ניתוחים/יום, 30 אימותים כל אחד | 9,000 | ~$9 |
| 50 ניתוחים/יום | 45,000 | ~$45 |
| 200 ניתוחים/יום (שימוש כבד) | 180,000 | ~$180 |
| **ללא rate limit — abuse** | **1,000,000+** | **$1,000+** |

→ **rate limiting + credit system = הכרחי**

---

*דוח זה נוצר מסקירת קוד מלאה של כל קבצי המערכת.*
*יש לטפל בפריטים מסומנים 🔴 לפני כל deploy לפרודקשן.*
