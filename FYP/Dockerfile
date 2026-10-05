# Flask API + PDAL, built from the same environment.yml used for local development.
# "2" is a rolling tag; pin a full version (or a sha256 digest) once the build works.
FROM mambaorg/micromamba:2

# Install dependencies first so this layer is cached unless environment.yml changes.
# gunicorn is added here rather than in environment.yml because it does not run on Windows.
COPY --chown=$MAMBA_USER:$MAMBA_USER environment.yml /tmp/environment.yml
RUN micromamba install -y -n base -f /tmp/environment.yml \
    && micromamba install -y -n base -c conda-forge gunicorn \
    && micromamba clean --all --yes

# Create the app and upload folders, owned by the non-root user the image runs as
USER root
RUN mkdir -p /app/data && chown -R $MAMBA_USER:$MAMBA_USER /app
USER $MAMBA_USER

WORKDIR /app
COPY --chown=$MAMBA_USER:$MAMBA_USER . .

ENV STORAGE_DIR=/app/data \
    PYTHONUNBUFFERED=1

EXPOSE 5000

# The image's entrypoint activates the conda environment, so gunicorn and pdal are on PATH.
# 2 workers x 4 threads: /points already runs its own thread pool per request.
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--threads", "4", "--timeout", "120", "app:app"]
