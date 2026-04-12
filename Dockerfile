FROM python:3.13-slim

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir .

COPY . .

EXPOSE ${MCP_PORT:-8000}

CMD ["python", "main.py"]
