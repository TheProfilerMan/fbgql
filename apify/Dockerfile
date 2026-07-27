# Apify actor image.
#
# IMPORTANT: build with the REPOSITORY ROOT as the Docker build context (this is a
# monorepo — the actor is a thin adapter over the ../src core package). On the Apify
# platform, set the actor's Dockerfile path to `apify/Dockerfile`; Apify uses the repo
# root as the build context, so the COPY paths below resolve.
FROM apify/actor-python:3.12

# Install the core package (built from src via hatchling) + the Apify SDK.
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir ".[apify]"

# The thin actor adapter (a `src` package: __main__.py runs main()).
COPY apify/src ./src

CMD ["python", "-m", "src"]
