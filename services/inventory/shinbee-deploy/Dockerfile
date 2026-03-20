ARG INVENTREE_TAG=stable
FROM inventree/inventree:${INVENTREE_TAG}

# Install uWSGI (requires compilation)
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc python3-dev \
    && pip install --no-cache-dir uwsgi \
    && apt-get purge -y gcc python3-dev \
    && apt-get autoremove -y \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Create socket directories
RUN mkdir -p /var/run/uwsgi /var/run/mysqld

# Copy deployment config files
COPY uwsgi.ini /home/inventree/uwsgi.ini
COPY config.yaml /home/inventree/config.yaml.default
COPY init-wrapper.sh /home/inventree/init-wrapper.sh
RUN sed -i 's/\r$//' /home/inventree/init-wrapper.sh /home/inventree/uwsgi.ini /home/inventree/config.yaml.default \
    && chmod +x /home/inventree/init-wrapper.sh

# Override entrypoint to use our wrapper (which reads Docker secrets)
ENTRYPOINT ["/bin/bash", "/home/inventree/init-wrapper.sh"]

# Default command: start uWSGI
CMD ["uwsgi", "--ini", "/home/inventree/uwsgi.ini"]
