FROM python:3.12-slim

RUN pip install --no-cache-dir --upgrade pip

COPY notifier/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY notifier/notify.py /opt/radicale-notifier/notify.py
COPY docker/notifier/entrypoint.sh /opt/radicale-notifier/entrypoint.sh
RUN chmod +x /opt/radicale-notifier/entrypoint.sh

CMD ["/opt/radicale-notifier/entrypoint.sh"]
