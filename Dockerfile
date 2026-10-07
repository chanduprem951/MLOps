FROM cgr.dev/chainguard/python:latest-dev AS build
USER root
WORKDIR /service
COPY requirements.txt .
RUN python -c "import sys; assert sys.version_info[:2] == (3, 14), 'Review runtime update before building'" \
    && python -m venv --without-pip /venv \
    && pip --python /venv/bin/python install --no-cache-dir --only-binary=:all: -r requirements.txt

FROM cgr.dev/chainguard/python:latest
ENV PATH="/venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /service
COPY --from=build /venv /venv
COPY app app
COPY ml ml
COPY scripts scripts
COPY artifacts/model.joblib artifacts/manifest.json artifacts/
USER 65532:65532
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD ["/venv/bin/python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/ready')"]
ENTRYPOINT ["/venv/bin/python"]
CMD ["-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
