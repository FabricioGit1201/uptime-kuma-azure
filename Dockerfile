FROM louislam/uptime-kuma:2

ENV DATA_DIR=/home/uptime-kuma-data

COPY azure-entrypoint.sh /app/azure-entrypoint.sh

RUN chmod +x /app/azure-entrypoint.sh

CMD ["/app/azure-entrypoint.sh"]
