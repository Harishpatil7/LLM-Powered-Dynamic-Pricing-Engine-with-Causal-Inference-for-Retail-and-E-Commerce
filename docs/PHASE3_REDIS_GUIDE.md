# Phase 3: In-Memory Caching & Rate Limiting (Redis) Deep Dive

Welcome to Phase 3 of the SDE production hardening track. This guide covers how in-memory key-value caching, eviction policies, distributed rate limiting, and graceful degradation work in high-scale enterprise architectures.

---

## 1. What is Redis & Why Is It Ultra-Fast?

### Memory vs. Disk Latency Hierarchy
In software engineering, understanding latency orders of magnitude is essential for system design:

| Storage Medium | Typical Latency | Real-World Analogy |
| :--- | :--- | :--- |
| **CPU L1 Cache** | ~0.5 nanoseconds | 1 heart beat |
| **RAM (Redis)** | ~100 nanoseconds | 3 minutes |
| **NVMe SSD (PostgreSQL/MySQL)** | ~50 microseconds | 2 days |
| **Mechanical HDD** | ~5 milliseconds | 3 months |
| **Internet Round-Trip (LLM API Call)** | ~1,500 milliseconds (1.5s) | 2.5 years |

Calling the live Gemini API takes **1,500ms (1.5 seconds)**. 
Querying a relational database on disk takes **10–50ms**.
Reading a cached key from Redis in RAM takes **< 1ms (sub-millisecond)**!

### Why is Redis Single-Threaded Yet Fast?
A common interview question: *"How can Redis handle 100,000 requests per second if it is single-threaded?"*
1. **No Context Switching or Thread Contention**: Multi-threaded servers spend significant CPU time on thread scheduling, lock synchronization (mutexes), and cache coherency. Redis avoids all lock contention.
2. **I/O Multiplexing (`epoll` / `kqueue`)**: Redis uses an event loop operating on Linux's non-blocking `epoll` system call, monitoring thousands of client sockets simultaneously on a single CPU core.
3. **RAM Execution**: Memory access is pure electronic hardware bus transfer without mechanical disk heads or flash block erase cycles.

---

## 2. Caching Strategies: Cache-Aside (Lazy Loading)

In `backend/api/routes/reports.py` and `backend/services/cache_service.py`, we implemented the **Cache-Aside Pattern**:

```
Client Request
      │
      ▼
Check Redis Cache? ──[Cache Hit]──▶ Return Cached Report (<10ms, $0 Cost)
      │
 [Cache Miss]
      ▼
Query Database Evidence & Generate Gemini Report (1,500ms)
      │
      ▼
Write Report to Redis with TTL (e.g. 1 Hour)
      │
      ▼
Return Report to Client
```

### Why Cache-Aside?
- **Resilience**: If Redis crashes, the application continues to function normally by fetching directly from the database and LLM (Graceful Degradation).
- **Cost Efficiency**: Only frequently requested data occupies precious RAM; inactive SKUs are never cached.

---

## 3. The Three Classic Caching Pitfalls & How We Solve Them

### 1. Cache Invalidation
> *"There are only two hard things in Computer Science: cache invalidation and naming things."* — Phil Karlton

- **The Problem**: If a user uploads new sales data or runs a new Causal Inference analysis for `SKU-001`, a naive cache would keep returning the old pricing report for the next hour (stale data).
- **Our Solution (`Event-Driven Write-Invalidation`)**:
  In `backend/api/routes/causal.py`, the moment a causal analysis run completes and commits to the database:
  ```python
  invalidate_product_cache(retailer_id, product_id)
  ```
  This immediately purges all keys matching `llm_dpeci:report:{retailer}:{product}:*`, guaranteeing that the next report request always generates fresh evidence.

### 2. Cache Eviction Policies (`allkeys-lru`)
- In `docker-compose.yml`, we configured Redis with:
  ```bash
  --maxmemory 256mb --maxmemory-policy allkeys-lru
  ```
- **LRU (Least Recently Used)**: If Redis reaches its 256MB memory cap, it automatically evicts the keys that haven't been read in the longest time, preventing out-of-memory (OOM) crashes.

### 3. Cache Stampede (Thundering Herd)
- **The Problem**: If a popular SKU's cache key expires, 500 simultaneous users might trigger 500 parallel expensive LLM calls at the exact same millisecond.
- **The Defense**: Setting randomized TTL jitter (e.g., 3600 ± 300 seconds) or using mutex locks (`SETNX`) so only one request regenerates the cache while others wait.

---

## 4. API Rate Limiting (Token Bucket / Fixed Window)

In `check_rate_limit()` inside `backend/services/cache_service.py`:
- We implemented an atomic counter using Redis `INCR` + `EXPIRE`.
- If a client exceeds 20 requests/minute, the API responds with:
  - **HTTP 429 Too Many Requests**
  - **Header `Retry-After: <seconds>`**
- **SDE Defense Concept (Fail-Open vs. Fail-Closed)**:
  - For **authentication security** (brute-force defense), rate limiters should fail-closed (block traffic if Redis is down).
  - For **business report generation**, rate limiters should fail-open (allow requests if Redis is temporarily unreachable so paying customers are not blocked).

---

## 5. SDE Placement Interview Flashcards (Redis & Caching)

### Q1: *"What is the difference between Cache-Aside and Write-Through caching?"*
> **Answer:** *"In Cache-Aside, the application is responsible for reading and writing from both the cache and the storage: it checks the cache first, and on a miss, reads from the database and populates the cache. In Write-Through, the application treats the cache as the primary data store: whenever a write occurs, the cache synchronously writes to the database before acknowledging success."*

### Q2: *"How does Redis persist data if it runs in RAM?"*
> **Answer:** *"Redis provides two persistence mechanisms:
> 1. **RDB (Redis Database Snapshots)**: Point-in-time binary snapshots written to disk at specified intervals.
> 2. **AOF (Append-Only File)**: Logs every write command received by the server to disk.
> In our `docker-compose.yml`, we enabled `--appendonly yes` to guarantee high durability across container restarts."*

### Q3: *"How would you design a distributed rate limiter across multiple web servers?"*
> **Answer:** *"A local in-memory counter on a single server fails when traffic is load-balanced across multiple instances. By using a centralized in-memory store like Redis, all web servers execute an atomic `INCR` command on a shared key (`ratelimit:{user_id}:{window}`). Since Redis operations are atomic, race conditions are eliminated across distributed web servers."*
