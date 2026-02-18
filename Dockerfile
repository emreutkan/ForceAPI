FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    postgresql-client \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# docker-compose will create these directories, but it's a good practice to have it here too
# to ensure they exist and have the right permissions (777)
# or else, if you ever run the container without Docker Compose, the app won't crash looking for those folders.
RUN mkdir -p staticfiles media logs

# this actually does nothing, but it's a good practice to have it, docker-compose is the one that exposes the port
EXPOSE 8000 

# again, this actually does nothing, but it's a good practice to have it, docker-compose will override this command with the one in the docker-compose.yml file
# so if you ever run the container without Docker Compose, the app won't crash looking for the command.
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "force.wsgi:application"]