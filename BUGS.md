## BUGS — E2E Validation

### 1) Docker daemon לא זמין בסביבה
**Status:** Open  
**Reproduction:**
```bash
DOC1=/tmp/gp_doc1.pdf DOC2=/tmp/gp_doc2.pdf ./scripts/golden_path.sh
```
**Observed:**
```
docker.errors.DockerException: Error while fetching server API version: Not supported URL scheme http+docker
```
**Impact:** אין אפשרות להריץ E2E מלא (כולל אימון/ייצוא) בסביבה זו.  
**Fix:** להריץ Docker daemon בסביבה עם init/systemd או לאפשר docker socket תקין.

