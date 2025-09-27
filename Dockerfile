# Use official Python image as base
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Set environment variables (optional)
ENV PYTHONUNBUFFERED=1

# Command to run the bot
CMD ["python", "bot.py"]



# to build : docker build -t dodo-bot .
# to run : docker run --rm dodo-bot 