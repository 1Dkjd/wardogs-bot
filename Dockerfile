FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 MPLCONFIGDIR=/tmp/mpl
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY *.py .
COPY fonts/ fonts/
VOLUME /data
CMD ["python", "bot.py"]
