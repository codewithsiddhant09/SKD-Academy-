# Production Deployment Guide

## 1. Environment Preparation

- Use Python 3.12 runtime.
- Configure `.env` with production values.
- Store secrets in a secret manager (Azure Key Vault, AWS Secrets Manager, etc).

Required variables:

- `OPENAI_API_KEY`
- `OPENAI_MODEL`
- `OPENAI_EMBEDDING_MODEL`
- `CATEGORIES_API_URL`
- `SALON_INFO_API_URL`
- `CATEGORIES_CACHE_TTL_SECONDS`
- `RAG_PERSIST_DIRECTORY`

## 2. Container Deployment

Build image:

```bash
docker build -t bookly-ai-chatbot:latest .
```

Run container:

```bash
docker run -d \
  --name bookly-ai \
  -p 8000:8000 \
  --env-file .env \
  bookly-ai-chatbot:latest
```

## 3. Reverse Proxy

Place NGINX or API Gateway in front of service:

- TLS termination
- Rate limiting
- IP allow-listing for internal APIs
- Request body limits

## 4. Scalability

- Run multiple app replicas behind load balancer.
- Move in-memory conversation store to Redis for horizontal scaling.
- Use persistent Chroma volume or managed vector DB.

## 5. Observability

- Export logs to centralized platform.
- Add metrics for latency, error rate, token usage.
- Track per-intent success and booking conversion.

## 6. Reliability

- Health checks: `GET /health`.
- Add circuit breaker around upstream APIs.
- Set conservative timeouts and retry policies.

## 7. Security

- Never expose raw OpenAI key in client apps.
- Keep `VERIFY_SSL=true` for production.
- Enforce auth on all public endpoints (JWT/API key).
- Add WAF and abuse protection on chat endpoint.

## 8. Recommended Next Production Steps

1. Replace mock salon source with real discovery/search API.
2. Persist bookings in transactional database.
3. Add Redis-backed conversation memory.
4. Add authentication and role-based access.
5. Add CI/CD with tests, linting, and SAST.
