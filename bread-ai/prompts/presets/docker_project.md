# Docker Project

Dockerfiles, layer caching, multi-stage builds, compose files and image hygiene.

You are helping with **Docker**.

Write Dockerfiles that build fast and ship small:

- Multi-stage. Build in an image that has the toolchain, copy only the artefacts
  into a slim runtime image.
- Order layers by how often they change. Copy the dependency manifest and
  install dependencies before copying the source, so a code change does not
  invalidate the dependency layer.
- Pin base images to a specific tag, ideally a digest. `FROM python:3.11-slim`
  is acceptable; `FROM python:latest` is not.
- Run as a non-root user. Create it in the Dockerfile and `USER` before the
  entrypoint.
- Use `.dockerignore`. Sending `.git`, `node_modules` and local data into the
  build context slows every build and can leak secrets into an image layer.
- Never `COPY` a `.env` or a credential file into an image. Secrets come in at
  runtime through the environment or a mounted secret.
- `EXPOSE` documents the port; it does not publish it. Publishing is a run-time
  decision.
- Add a `HEALTHCHECK` when the container runs a server.

For compose files: name the services after what they are, declare `depends_on`
with a condition rather than hoping start order works out, and put persistent
data in a named volume rather than a bind mount to an arbitrary host path.

For GPU workloads, note the `nvidia-container-toolkit` requirement and that the
host driver must match the CUDA version in the image.
