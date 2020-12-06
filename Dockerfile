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

# Make the instance directory
RUN mkdir /resumable/instance

# Grant the "nobody" user access and switch to it
RUN chown -R nobody /resumable
USER nobody

# Expose port 5000 for flask app
EXPOSE 5000

# Spawn the flask app
CMD ["flask", "run"]