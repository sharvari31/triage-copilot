---
id: KB-015
title: API rate limits and 429 errors
category: technical
---
# API rate limits and 429 errors

The API allows 100 requests per minute per API key. Requests above the limit receive HTTP **429 Too Many Requests** with a `Retry-After` header. Use exponential backoff and batch endpoints where possible. Higher limits are available on the Business plan. Invalid or revoked keys return 401; regenerate keys under **Settings > Developers**.
