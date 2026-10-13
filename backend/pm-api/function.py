"""
AWS Lambda entry point for the ACME project-tracking API.

The FastAPI application lives in ``app``; Mangum adapts Lambda Function URL
events (API Gateway v2 payload format) to ASGI. CloudFront forwards requests
with the ``/api/pm-api`` prefix intact while the local proxy strips it, and
``app.main`` handles both by treating the prefix as the ASGI root path.
"""

from mangum import Mangum

from app.main import app

# Lambda invocations are one request at a time, so ASGI lifespan events are unnecessary.
handler = Mangum(app, lifespan="off")

# Main entry point for local testing without LocalStack: `python function.py`
if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
