FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download HuggingFace models into the image so they are cached
# and don't need to be downloaded on every container start.
# Legal-HeBERT (semantic embeddings) + Legal QA (fact extraction)
RUN python -c "\
from transformers import AutoTokenizer, AutoModel, pipeline; \
AutoTokenizer.from_pretrained('avichr/Legal-heBERT'); \
AutoModel.from_pretrained('avichr/Legal-heBERT'); \
pipeline('question-answering', model='shay681/HeBERT_finetuned_Legal_Clauses', \
         tokenizer='shay681/HeBERT_finetuned_Legal_Clauses'); \
print('Models cached successfully') \
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
