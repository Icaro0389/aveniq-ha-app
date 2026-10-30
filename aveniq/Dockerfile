ARG BUILD_FROM=python:3.12-alpine
FROM ${BUILD_FROM}
ENV PYTHONUNBUFFERED=1
WORKDIR /app
COPY app/ /app/
EXPOSE 8099
CMD ["python", "-u", "server.py"]
