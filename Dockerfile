FROM python:3.13-slim

WORKDIR /app

# Copy the requirements file and install dependencies
# We simulate a requirements.txt creation in the dockerfile or copy it
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Expose the port
EXPOSE 8080

# Set environment variables for production
ENV PORT=8080

# Command to run the application (ADK-native server pattern via standard Python execution)
CMD ["python", "backend/server.py"]
