FROM python:3.7-alpine
WORKDIR /resumable

# Copy necesssary files into container
COPY . /resumable/

# Set constant environment variables for flask
ENV FLASK_APP=app
ENV FLASK_RUN_HOST=0.0.0.0

# Install necessary packages
RUN apk add --no-cache gcc musl-dev linux-headers
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Create a non-root user and switch to it
RUN addgroup -S dockgrp && adduser -S dockusr -G dockgrp
RUN chown -R dockusr /resumable
USER dockusr

# Expose port 5000 for flask app
EXPOSE 5000

# Spawn the flask app
CMD ["flask", "run"]