# Hugging Face Spaces (Docker SDK): the website + background runs on one small server.
FROM python:3.11-slim

RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user PATH=/home/user/.local/bin:$PATH PYTHONUNBUFFERED=1 RUNNER=process
WORKDIR /home/user/app

COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt
COPY --chown=user . .

EXPOSE 7860
CMD ["uvicorn", "api.index:app", "--host", "0.0.0.0", "--port", "7860", "--proxy-headers"]
