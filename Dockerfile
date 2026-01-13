FROM python:3.11-slim

WORKDIR /app

# Copy requirements first for better caching
COPY copilot_agent/requirements.txt ./copilot_agent/
RUN pip install --no-cache-dir -r copilot_agent/requirements.txt

# Copy the rest of the application
COPY . .

# Expose port
EXPOSE 8000

# Set working directory to copilot_agent
WORKDIR /app/copilot_agent

# Run the FastAPI application
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
