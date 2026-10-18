FROM python:3.11.17-slim-bookworm
ARG RUNNER_SHA256=54853fcca3afb7a3726378ee197282939c5bae8978ef0d02b9926b1685d52deb
COPY gitlab-runner-linux-arm64 /usr/local/bin/gitlab-runner
RUN echo "${RUNNER_SHA256}  /usr/local/bin/gitlab-runner" | sha256sum -c - \
    && chmod 755 /usr/local/bin/gitlab-runner \
    && sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources \
    && apt-get -o Acquire::ForceIPv4=true -o Acquire::https::Timeout=30 update \
    && apt-get -o Acquire::ForceIPv4=true -o Acquire::https::Timeout=30 install -y --no-install-recommends bash git curl ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && python -m pip install --no-cache-dir --disable-pip-version-check uv==0.10.9 \
    && useradd --uid 1000 --create-home --shell /bin/bash gitlab-runner \
    && chmod 700 /home/gitlab-runner \
    && test ! -e /usr/bin/sudo
ENTRYPOINT ["gitlab-runner"]
CMD ["run", "--config", "/etc/gitlab-runner/config.toml", "--working-directory", "/home/gitlab-runner", "--user", "gitlab-runner"]
