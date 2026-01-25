## BUGS — E2E Validation

### 1) Docker Compose missing in environment
**Status:** Open  
**Reproduction:**
```bash
DOC1=/tmp/gp_doc1.pdf DOC2=/tmp/gp_doc2.pdf ./scripts/golden_path.sh
```
**Observed:**
```
Docker Compose לא נמצא (נדרש docker compose או docker-compose)
```
**Impact:** אין אפשרות להריץ E2E מלא (כולל אימון/ייצוא) בסביבה זו.  
**Fix:** התקנת Docker + docker compose plugin (או docker-compose) והוספתם ל־PATH.

