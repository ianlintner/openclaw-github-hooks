FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .

USER 1000:1000
EXPOSE 8766
CMD ["sh", "-c", "uvicorn openclaw_github_hooks.main:create_app --factory --host ${GH_HOOKS_HOST:-0.0.0.0} --port ${GH_HOOKS_PORT:-8766}"]
