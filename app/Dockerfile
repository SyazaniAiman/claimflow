# ---- ClaimFlow web portal + API -------------------------------------------
# Small base image: less software inside means fewer known vulnerabilities.
FROM python:3.11-slim
RUN pip install --no-cache-dir --upgrade "setuptools>=80.9.0" "wheel>=0.46.2"

# Do not write .pyc files, do not buffer logs (so they appear immediately).
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app

# Install dependencies first, on their own layer, so that changing your code
# does not force a re-download of every package on the next build.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Never run as root.  If the app is ever compromised, the attacker does not
# start with administrative rights inside the container.
RUN useradd --create-home --shell /usr/sbin/nologin appuser \
 && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# gunicorn, not the Flask development server: the dev server is single
# threaded and is not meant to face real traffic.
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", \
     "--timeout", "60", "--access-logfile", "-", "app:app"]
