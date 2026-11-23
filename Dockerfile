
FROM louislam/uptime-kuma:2.5.12

ENV DATA_DIR=/home/uptime-kuma-data

COPY azure-entrypoint.sh /app/azure-entrypoint.sh
COPY restore-uptime-kuma.py /app/restore-uptime-kuma.py
COPY prepare-manual-restore.py /app/prepare-manual-restore.py

COPY App_Data/jobs/triggered/KumaRestoreManual/run.sh /home/site/wwwroot/App_Data/jobs/triggered/KumaRestoreManual/run.sh

RUN chmod +x /app/azure-entrypoint.sh \
    && chmod +x /app/restore-uptime-kuma.py \
    && chmod +x /app/prepare-manual-restore.py \
    && chmod +x /home/site/wwwroot/App_Data/jobs/triggered/KumaRestoreManual/run.sh

CMD ["/app/azure-entrypoint.sh"]
