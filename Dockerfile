FROM tiangolo/uvicorn-gunicorn-fastapi:python3.11

WORKDIR /code

COPY ./requirements.txt /code/requirements.txt

# Install requirements
RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

# Copy folders
COPY ./.git /code/.git
COPY ./app /code/app

EXPOSE 80

# Check container status when running
HEALTHCHECK --interval=10s --timeout=10s --retries=3 \
  CMD curl -f http://localhost:${PORT}/health-check || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "80"]
