# Generic CLI image (no browser — scraping is pure HTTP).
# Build with the repository ROOT as the build context:
#     docker build -f docker/Dockerfile -t fbgql .
# Run (cookies mounted in):
#     docker run --rm -v "$PWD/cookies.json:/data/cookies.json" fbgql \
#       scrape --page ZainSudan --posts 20 --cookies /data/cookies.json --out /data/out.json
FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install .

ENTRYPOINT ["fbgql"]
CMD ["--help"]
