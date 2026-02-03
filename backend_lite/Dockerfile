FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download HuggingFace models into the image so they are cached
# and don't need to be downloaded on every container start.
# Legal-HeBERT (semantic embeddings) + Legal QA (fact extraction)
#
# Memory tiers (set env vars in Railway dashboard):
#   >= 2GB RAM: Both models (default) — best accuracy
#   >= 1GB RAM: DISABLE_QA_MODEL=1    — HeBERT only, regex QA fallback
#   <  1GB RAM: DISABLE_HEBERT=1 DISABLE_QA_MODEL=1 — TF-IDF + regex only
#
# To use a custom fine-tuned model, set in Railway:
#   LEGAL_HEBERT_MODEL=your-username/Legal-heBERT-trial-courts
ARG LEGAL_HEBERT_MODEL=avichr/Legal-heBERT
RUN python -c "\
import os; \
model = os.environ.get('LEGAL_HEBERT_MODEL', 'avichr/Legal-heBERT'); \
from transformers import AutoTokenizer, AutoModel, pipeline; \
AutoTokenizer.from_pretrained(model); \
AutoModel.from_pretrained(model); \
pipeline('question-answering', model='shay681/HeBERT_finetuned_Legal_Clauses', \
         tokenizer='shay681/HeBERT_finetuned_Legal_Clauses'); \
print(f'Models cached: {model} + Legal QA') \
"

# Copy all code to backend_lite/
COPY . ./backend_lite/

# Create __init__.py if missing
RUN touch ./backend_lite/__init__.py

# Make start scripts executable
RUN chmod +x ./backend_lite/start.sh ./backend_lite/start_worker.sh

# Environment
ENV LLM_MODE=none
ENV PORT=8000
ENV PYTHONPATH=/app

EXPOSE 8000

# Run with shell wrapper to expand $PORT variable
CMD ["sh", "-c", "uvicorn backend_lite.api:app --host 0.0.0.0 --port ${PORT:-8000}"]
