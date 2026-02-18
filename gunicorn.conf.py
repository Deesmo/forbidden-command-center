# Gunicorn configuration for Forbidden Command Center
# Default timeout of 30s is too low for AI API calls (article generation, image gen)
# This file is auto-detected by Gunicorn even without --config flag

timeout = 120          # 2 minutes - AI generation can take 30-90 seconds
workers = 2            # Match render.yaml
threads = 2            # Match render.yaml
graceful_timeout = 30  # Time for graceful shutdown
keepalive = 5          # Keep-alive connections
