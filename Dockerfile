FROM louislam/uptime-kuma:2

ENV DATA_DIR=/home/uptime-kuma-data

COPY azure-entrypoint.sh /app/azure-entrypoint.sh
COPY restore-uptime-kuma.py /app/restore-uptime-kuma.py

RUN chmod +x /app/azure-entrypoint.sh \
    && chmod +x /app/restore-uptime-kuma.py

CMD ["/app/azure-entrypoint.sh"]
