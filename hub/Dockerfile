FROM python:3.12-alpine
RUN apk add --no-cache git && git config --system --add safe.directory '*'
WORKDIR /app
COPY serveur.py .
COPY static ./static
CMD ["python", "-u", "serveur.py"]
