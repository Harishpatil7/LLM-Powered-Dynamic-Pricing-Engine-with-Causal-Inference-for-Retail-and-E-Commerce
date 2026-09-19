# Phase 1: Containerization & Orchestration Deep Dive

Welcome to Phase 1 of the Software Development Engineer (SDE) production hardening track. This guide covers everything you need to know about how Docker, Multi-Stage Builds, Nginx, and Docker Compose work—from kernel-level primitives to system design trade-offs and interview questions.

---

## 1. What is Docker & How Does It Work Under the Hood?

### The Core Problem It Solves
In software engineering, the classic failure mode is **environment drift**:
> *"It runs on my Windows development machine, but crashes when deployed to Linux Ubuntu in the cloud due to missing C libraries, differing Python minor versions, or path separator discrepancies."*

Docker guarantees **idempotent environments**: code runs inside identical, isolated containers regardless of host operating system.

### Containers vs. Virtual Machines (VMs)
This is a standard SDE interview question:

| Dimension | Virtual Machine (VM) | Docker Container |
| :--- | :--- | :--- |
| **Architecture** | Hypervisor (Type 1 or 2) emulating full hardware | Process-level isolation sharing host OS kernel |
| **Guest OS** | Full guest OS (e.g., Ubuntu, Windows Server) | No guest OS; only userland binaries & libraries |
| **Memory Footprint** | Gigabytes (GBs) per VM | Megabytes (MBs) per container |
| **Startup Time** | 30 to 120 seconds | < 500 milliseconds |
| **Isolation Mechanism** | Hardware hypervisor isolation | Linux Kernel primitives (Namespaces & Cgroups) |

### The Three Linux Kernel Pillars of Docker
Under the hood on Linux (or WSL2 on Windows), Docker relies on three kernel features:
1. **Linux Namespaces (Process Isolation)**:
   - `PID Namespace`: Container processes only see themselves (the container process believes it is PID 1).
   - `NET Namespace`: Container gets its own virtual network interfaces, IP addresses, and routing tables.
   - `MNT Namespace`: Container has its own isolated filesystem mount points.
   - `USER Namespace`: Maps container root (UID 0) to an unprivileged user on the host system.
2. **Control Groups (Cgroups) (Resource Limiting)**:
   - Restricts and meters CPU, memory, disk I/O, and network bandwidth so one runaway container cannot crash the host server.
3. **OverlayFS (Union File System)**:
   - Stacks read-only image layers on top of each other. When a container writes data, it uses a thin **Copy-On-Write (CoW)** layer on top.

---

## 2. Deep-Dive: Backend Multi-Stage Dockerfile

Let us examine the file `Dockerfile` created in the repository root:

```dockerfile
# STAGE 1: BUILDER
FROM python:3.11-slim-bookworm AS builder
```
- **Why `python:3.11-slim-bookworm`?**
  - Standard `python:3.11` includes hundreds of development packages you never need, resulting in a 1.2GB image.
  - Alpine Linux (`python:3.11-alpine`) uses `musl libc` instead of `glibc`. Scientific packages like `scikit-learn`, `numpy`, and `scipy` do not provide official precompiled binary wheels for `musl`, forcing pip to compile them from C++ source (taking 40+ minutes to build!).
  - `slim-bookworm` (Debian 12 slim) uses standard `glibc`, allowing pip to install precompiled binary wheels in seconds while remaining under 180MB.

```dockerfile
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1
```
- `PYTHONDONTWRITEBYTECODE=1`: Prevents Python from writing `.pyc` files to disk. In a container, write operations to the CoW layer have an overhead; code is read directly from memory.
- `PYTHONUNBUFFERED=1`: Ensures that Python `print()` and logging statements are immediately flushed to `stdout` and `stderr` instead of buffered in memory. This is critical for Docker logging drivers and observability platforms (Datadog, Grafana Loki).
- `PIP_NO_CACHE_DIR=1`: Disables pip's internal cache, saving hundreds of megabytes in image size.

```dockerfile
WORKDIR /build
COPY requirements.txt .
RUN pip install --upgrade pip setuptools wheel && \
    pip install -r requirements.txt
```
- **The Golden Rule of Docker Layer Caching**:
  - Docker caches the result of every command.
  - If we ran `COPY . .` first, changing a single character in a Python file would invalidate the cache and force Docker to re-download all 500MB of pip dependencies every single time!
  - By copying `requirements.txt` alone and installing dependencies *before* copying the code, Docker reuses the cached layer in subsequent builds in **0.1 seconds**.

```dockerfile
# STAGE 2: RUNTIME
FROM python:3.11-slim-bookworm AS runner
...
COPY --from=builder --chown=appuser:appgroup /opt/venv /opt/venv
```
- **Multi-Stage Build Rationale**:
  - The build tools (`gcc`, `g++`, `build-essential`, `libffi-dev`) remain confined to Stage 1 (`builder`) and are **never copied into the final image**.
  - Only the resulting Python virtualenv `/opt/venv` is copied into the minimal runtime stage.
  - **Result**: Small image size (~220MB vs 1.4GB) and minimized CVE security vulnerabilities.

```dockerfile
RUN groupadd -g 1001 appgroup && \
    useradd -u 1001 -g appgroup -m -s /bin/bash appuser
...
USER appuser
```
- **Enterprise Security: Principle of Least Privilege**:
  - By default, Docker containers run as `root` (UID 0).
  - If an attacker discovers a Remote Code Execution (RCE) flaw in an API endpoint, they would gain root privileges inside the container, drastically increasing the risk of container escape.
  - Running as `appuser` (UID 1001) prevents the application from modifying system binaries or accessing unauthorized files.

```dockerfile
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1
```
- **Docker Healthcheck**:
  - Docker checks `/health` every 30 seconds.
  - If the backend freezes or crashes, Docker marks the container as `unhealthy`, enabling container orchestrators (Docker Swarm, Kubernetes) to automatically restart or route traffic away from it.

---

## 3. Deep-Dive: Frontend React & Nginx Containerization

Look at `frontend/Dockerfile` and `frontend/nginx.conf`:

### Why Not Run `npm run dev` in Production?
The Vite development server is designed for developer convenience with Hot Module Reloading (HMR) and source maps. It is single-threaded, uses high memory, and is not hardened against web attacks.
In production:
1. We run `npm run build` once inside Stage 1 (`node:20-alpine AS builder`). This minifies HTML, bundles JavaScript, compiles CSS, and produces static assets in `dist/`.
2. We discard Node.js entirely and copy the static files into **Nginx Alpine** (~25MB image footprint).

### How `frontend/nginx.conf` Solves Production Problems
1. **Gzip Compression**: Compresses text/JS/CSS on the fly, reducing bandwidth consumption by ~70%.
2. **Single Page Application (SPA) Routing**:
   ```nginx
   location / {
       try_files $uri $uri/ /index.html;
   }
   ```
   In React, client-side routing means `/workspace` or `/pricing` exists only in the browser's JavaScript router. Without `try_files`, refreshing `/workspace` returns an Nginx `404 Not Found`. `try_files` tells Nginx: *"If the physical file doesn't exist, serve `index.html` and let React handle the route."*
3. **API Reverse Proxying (Eliminates CORS)**:
   ```nginx
   location /api/ {
       proxy_pass http://backend:8000;
   }
   ```
   Both frontend and backend appear to come from the same domain (`http://localhost:3000`). Browsers never trigger Cross-Origin Resource Sharing (CORS) preflight requests, reducing network overhead.

---

## 4. Deep-Dive: Docker Compose Multi-Container Topology

Let us analyze `docker-compose.yml`:

```
                    ┌────────────────────────┐
                    │      Host Machine      │
                    │   (Browser / Client)   │
                    └───────────┬────────────┘
                                │
               HTTP :3000       │       HTTP :8000
             (Frontend UI)      │       (FastAPI API)
                                ▼
       ┌────────────────────────────────────────────────────────┐
       │             User-Defined Bridge Network                │
       │                   (dpeci_network)                      │
       │                                                        │
       │   ┌────────────────────┐      ┌────────────────────┐   │
       │   │      frontend      │      │      backend       │   │
       │   │   (Nginx Alpine)   │─────▶│  (FastAPI / Uvicorn│   │
       │   └────────────────────┘      └─────────┬──────────┘   │
       │                                         │              │
       │                                         ▼              │
       │                        ┌────────────────┴───────────┐  │
       │                        ▼                            ▼  │
       │             ┌────────────────────┐        ┌─────────┴──┐
       │             │       redis        │        │     db     │
       │             │   (Redis 7 Alpine) │        │ (MySQL 8.0)│
       │             └────────────────────┘        └────────────┘
       └────────────────────────────────────────────────────────┘
```

### Key Orchestration Concepts

1. **Service Discovery & Built-in DNS**:
   - Inside `dpeci_network`, containers do NOT use `localhost` or hardcoded IP addresses.
   - Docker runs an embedded DNS server: the backend reaches MySQL simply by using hostname `db:3306`, and Redis via `redis:6379`.
2. **Orderly Bootstrapping (`depends_on` with `condition: service_healthy`)**:
   - A common race condition: The backend starts, tries to connect to the database, but MySQL is still initializing its storage tables, causing the backend to crash.
   - We configured:
     ```yaml
     depends_on:
       db:
         condition: service_healthy
       redis:
         condition: service_healthy
     ```
   - Docker Compose will hold the backend in check until MySQL passes its `mysqladmin ping` healthcheck!
3. **Data Persistence (Named Volumes)**:
   - Containers are ephemeral: destroying a container destroys its internal storage.
   - Named volumes (`mysql_data`, `redis_data`, `backend_artifacts`) mount host directories into the container, ensuring your database records and trained models persist across restarts.

---

## 5. How to Run & Verify

If Docker Desktop is installed on the machine:
```bash
# 1. Build and launch all 4 services in detached (background) mode
docker compose up --build -d

# 2. View running containers and health status
docker compose ps

# 3. Stream real-time logs from all services
docker compose logs -f

# 4. Tear down containers while preserving persistent database volumes
docker compose down
```

---

## 6. SDE Placement Interview Flashcards (Docker & Systems)

### Q1: *"Why do we use multi-stage builds in Docker?"*
> **Answer:** *"To separate the build environment from the runtime environment. In our backend, compilers like gcc and build-essential are needed to build C extensions for EconML and NumPy, but they are unnecessary and risky in production. Multi-stage builds allow us to compile in stage 1, copy only the compiled virtualenv into stage 2, and reduce the final image from 1.4GB to ~220MB while significantly minimizing security CVEs."*

### Q2: *"What is the difference between `CMD` and `ENTRYPOINT` in a Dockerfile?"*
> **Answer:** *"ENTRYPOINT sets the default executable for the container (e.g., `uvicorn`), while CMD provides default arguments that can be easily overridden from the command line. When both are used, CMD acts as default parameters appended to ENTRYPOINT."*

### Q3: *"How does Docker networking enable microservices to communicate?"*
> **Answer:** *"Docker Compose creates a user-defined bridge network with an internal DNS resolver. Each container registers its service name (e.g., `db`, `redis`, `backend`) as its hostname, allowing services to communicate by name without hardcoded IP addresses."*
