# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Container Documentation Scraper.

Phase 27: RAG Coverage

Comprehensive container guides covering:
- Docker basics and commands
- Dockerfile best practices
- Docker Compose
- Podman basics
- Container networking
- Container security
"""

import logging
from typing import List
from datetime import datetime
from pathlib import Path

from .base import BaseScraper, ScrapedDocument, ScraperConfig

logger = logging.getLogger('halbert')


class ContainersDocsScraper(BaseScraper):
    """Generates comprehensive container documentation."""
    
    def __init__(self, config: ScraperConfig):
        super().__init__(config)
    
    def get_source_name(self) -> str:
        return "containers-docs"
    
    def scrape(self) -> List[ScrapedDocument]:
        """Generate container documentation."""
        logger.info("Generating container documentation...")
        
        documents = []
        documents.extend(self._generate_guides())
        
        logger.info(f"Total container documents: {len(documents)}")
        return documents
    
    def _generate_guides(self) -> List[ScrapedDocument]:
        """Generate all container guides."""
        guides = []
        
        guides.append(self._docker_basics_guide())
        guides.append(self._dockerfile_guide())
        guides.append(self._docker_compose_guide())
        guides.append(self._podman_guide())
        guides.append(self._container_networking_guide())
        guides.append(self._container_volumes_guide())
        guides.append(self._container_security_guide())
        guides.append(self._troubleshooting_guide())
        
        return guides
    
    def _docker_basics_guide(self) -> ScrapedDocument:
        """Docker basics guide."""
        content = """# Docker Basics Guide

## Installation

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install docker.io
sudo systemctl enable --now docker

# Add user to docker group (logout required)
sudo usermod -aG docker $USER

# Verify
docker --version
docker run hello-world
```

## Container Lifecycle

```bash
# Run container
docker run nginx                       # Run and attach
docker run -d nginx                    # Detached (background)
docker run -it ubuntu bash             # Interactive with TTY
docker run --name mycontainer nginx    # Named container
docker run --rm nginx                  # Remove after exit

# List containers
docker ps                              # Running
docker ps -a                           # All
docker ps -q                           # IDs only

# Container operations
docker start container_name
docker stop container_name
docker restart container_name
docker pause container_name
docker unpause container_name

# Remove containers
docker rm container_name
docker rm -f container_name            # Force (running)
docker container prune                 # Remove all stopped
```

## Executing Commands

```bash
# Run command in container
docker exec container_name command
docker exec -it container_name bash    # Interactive shell
docker exec -u root container_name cmd # As specific user

# View logs
docker logs container_name
docker logs -f container_name          # Follow
docker logs --tail 100 container_name  # Last 100 lines
docker logs --since 1h container_name  # Last hour
```

## Port Mapping

```bash
# Map ports
docker run -p 8080:80 nginx            # Host:Container
docker run -p 80 nginx                 # Random host port
docker run -P nginx                    # All exposed ports
docker run -p 127.0.0.1:8080:80 nginx  # Bind to localhost

# Check port mapping
docker port container_name
```

## Environment Variables

```bash
# Set environment variables
docker run -e VAR=value nginx
docker run -e VAR1=val1 -e VAR2=val2 nginx
docker run --env-file .env nginx
```

## Image Management

```bash
# Pull images
docker pull nginx
docker pull nginx:1.21
docker pull nginx:latest

# List images
docker images
docker image ls

# Remove images
docker rmi image_name
docker rmi image_id
docker image prune                     # Remove unused
docker image prune -a                  # Remove all unused

# Search Docker Hub
docker search nginx

# Image info
docker inspect image_name
docker history image_name
```

## Container Info

```bash
# Inspect container
docker inspect container_name

# Resource usage
docker stats
docker stats container_name

# Processes
docker top container_name

# File changes
docker diff container_name

# Copy files
docker cp container_name:/path/file ./local
docker cp ./local container_name:/path/
```

## System Management

```bash
# Disk usage
docker system df

# Clean up everything
docker system prune                    # Unused data
docker system prune -a                 # Including images
docker system prune --volumes          # Including volumes

# System info
docker info
docker version
```
"""
        return ScrapedDocument(
            id=self._generate_id("docker-basics"),
            url="https://docs.docker.com/",
            title="Docker Basics Guide",
            content=content,
            source=self.get_source_name(),
            category="containers",
            tags=["docker", "containers", "linux"],
            scraped_at=datetime.utcnow().isoformat(),
            metadata={"type": "guide", "priority": "high"}
        )
    
    def _dockerfile_guide(self) -> ScrapedDocument:
        """Dockerfile guide."""
        content = """# Dockerfile Best Practices

## Basic Dockerfile

```dockerfile
# Base image
FROM ubuntu:22.04

# Metadata
LABEL maintainer="you@example.com"
LABEL version="1.0"

# Environment variables
ENV APP_HOME=/app
ENV NODE_ENV=production

# Working directory
WORKDIR $APP_HOME

# Copy files
COPY . .
COPY package*.json ./

# Run commands
RUN apt-get update && apt-get install -y \\
    package1 \\
    package2 \\
    && rm -rf /var/lib/apt/lists/*

# Expose port
EXPOSE 8080

# Default command
CMD ["./start.sh"]
```

## Instructions

```dockerfile
# FROM - Base image
FROM node:18-alpine
FROM python:3.11-slim
FROM scratch                           # Empty image

# WORKDIR - Set working directory
WORKDIR /app

# COPY - Copy files from build context
COPY . .
COPY --chown=user:group src/ /app/
COPY --from=builder /app/dist /app/    # Multi-stage

# ADD - Like COPY but can extract tar and fetch URLs
ADD archive.tar.gz /app/
ADD https://example.com/file /app/

# RUN - Execute command
RUN npm install
RUN apt-get update && apt-get install -y vim

# CMD - Default command (can be overridden)
CMD ["node", "app.js"]
CMD node app.js

# ENTRYPOINT - Main executable (harder to override)
ENTRYPOINT ["python"]
CMD ["app.py"]                         # Default args

# ENV - Environment variable
ENV PORT=8080
ENV NODE_ENV production

# ARG - Build-time variable
ARG VERSION=1.0
RUN echo $VERSION

# EXPOSE - Document port (doesn't publish)
EXPOSE 8080
EXPOSE 8080/tcp 8081/udp

# VOLUME - Mount point
VOLUME /data

# USER - Run as user
USER appuser
USER 1000:1000

# HEALTHCHECK
HEALTHCHECK --interval=30s --timeout=3s \\
    CMD curl -f http://localhost/ || exit 1
```

## Multi-stage Build

```dockerfile
# Build stage
FROM node:18 AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

# Production stage
FROM node:18-alpine
WORKDIR /app
COPY --from=builder /app/dist ./dist
COPY --from=builder /app/node_modules ./node_modules
EXPOSE 3000
CMD ["node", "dist/index.js"]
```

## Best Practices

```dockerfile
# 1. Use specific tags
FROM node:18.17.1-alpine    # Good
FROM node:latest            # Bad

# 2. Minimize layers
RUN apt-get update && \\
    apt-get install -y vim curl && \\
    rm -rf /var/lib/apt/lists/*

# 3. Order from least to most changing
COPY package*.json ./
RUN npm install
COPY . .                    # Source changes often

# 4. Use .dockerignore
# .dockerignore file:
# node_modules
# .git
# *.log
# Dockerfile

# 5. Don't run as root
RUN useradd -r appuser
USER appuser

# 6. Use COPY over ADD
COPY ./src /app/src         # Prefer this

# 7. Combine RUN commands
RUN apt-get update && apt-get install -y \\
    package1 \\
    package2 \\
    && rm -rf /var/lib/apt/lists/*
```

## Build Commands

```bash
# Build image
docker build -t myapp .
docker build -t myapp:1.0 .
docker build -f Dockerfile.prod -t myapp .

# Build with args
docker build --build-arg VERSION=1.0 -t myapp .

# No cache
docker build --no-cache -t myapp .

# Target specific stage
docker build --target builder -t myapp:builder .
```
"""
        return ScrapedDocument(
            id=self._generate_id("dockerfile-guide"),
            url="https://docs.docker.com/reference/dockerfile/",
            title="Dockerfile Best Practices",
            content=content,
            source=self.get_source_name(),
            category="containers",
            tags=["docker", "dockerfile", "containers", "best-practices"],
            scraped_at=datetime.utcnow().isoformat(),
            metadata={"type": "guide", "priority": "high"}
        )
    
    def _docker_compose_guide(self) -> ScrapedDocument:
        """Docker Compose guide."""
        content = """# Docker Compose Guide

## Basic docker-compose.yml

```yaml
version: '3.8'

services:
  web:
    image: nginx:alpine
    ports:
      - "80:80"
    volumes:
      - ./html:/usr/share/nginx/html
    depends_on:
      - api
    
  api:
    build: ./api
    ports:
      - "3000:3000"
    environment:
      - DATABASE_URL=postgres://db:5432/mydb
    depends_on:
      - db
    
  db:
    image: postgres:15
    volumes:
      - postgres_data:/var/lib/postgresql/data
    environment:
      POSTGRES_PASSWORD: secret

volumes:
  postgres_data:
```

## Commands

```bash
# Start services
docker compose up
docker compose up -d                   # Detached
docker compose up --build              # Rebuild images

# Stop services
docker compose down
docker compose down -v                 # Remove volumes
docker compose down --rmi all          # Remove images

# Service management
docker compose start
docker compose stop
docker compose restart
docker compose pause
docker compose unpause

# View status
docker compose ps
docker compose logs
docker compose logs -f service_name
docker compose top

# Execute command
docker compose exec service_name bash

# Scale services
docker compose up -d --scale web=3

# Build
docker compose build
docker compose build --no-cache
```

## Service Configuration

```yaml
services:
  app:
    # Image or build
    image: nginx:alpine
    build:
      context: ./app
      dockerfile: Dockerfile.prod
      args:
        - VERSION=1.0
    
    # Container name
    container_name: my-app
    
    # Port mapping
    ports:
      - "8080:80"
      - "127.0.0.1:3000:3000"
    
    # Environment
    environment:
      - NODE_ENV=production
      - DEBUG=false
    env_file:
      - .env
      - .env.local
    
    # Volumes
    volumes:
      - ./src:/app/src              # Bind mount
      - data:/app/data              # Named volume
      - /app/node_modules           # Anonymous volume
    
    # Networks
    networks:
      - frontend
      - backend
    
    # Dependencies
    depends_on:
      - db
      - redis
    depends_on:
      db:
        condition: service_healthy
    
    # Restart policy
    restart: unless-stopped
    # Options: no, always, on-failure, unless-stopped
    
    # Resource limits
    deploy:
      resources:
        limits:
          cpus: '0.5'
          memory: 512M
        reservations:
          memory: 256M
    
    # Health check
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
    
    # Command override
    command: ["npm", "start"]
    entrypoint: ["/entrypoint.sh"]
    
    # User
    user: "1000:1000"
    
    # Working directory
    working_dir: /app
```

## Networks

```yaml
services:
  web:
    networks:
      - frontend
  api:
    networks:
      - frontend
      - backend
  db:
    networks:
      - backend

networks:
  frontend:
  backend:
    driver: bridge
  external_net:
    external: true
    name: my-external-network
```

## Volumes

```yaml
services:
  db:
    volumes:
      - postgres_data:/var/lib/postgresql/data

volumes:
  postgres_data:
  
  # External volume
  shared_data:
    external: true
    
  # With options
  custom_volume:
    driver: local
    driver_opts:
      type: nfs
      o: addr=192.168.1.100,rw
      device: ":/path/to/share"
```

## Multiple Compose Files

```bash
# Override file
docker compose -f docker-compose.yml -f docker-compose.prod.yml up

# Default files: docker-compose.yml, docker-compose.override.yml
```
"""
        return ScrapedDocument(
            id=self._generate_id("docker-compose"),
            url="https://docs.docker.com/compose/",
            title="Docker Compose Guide",
            content=content,
            source=self.get_source_name(),
            category="containers",
            tags=["docker", "docker-compose", "containers", "orchestration"],
            scraped_at=datetime.utcnow().isoformat(),
            metadata={"type": "guide", "priority": "high"}
        )
    
    def _podman_guide(self) -> ScrapedDocument:
        """Podman guide."""
        content = """# Podman Guide

## Overview

Podman is a daemonless container engine compatible with Docker CLI.

**Key differences from Docker:**
- No daemon (rootless by default)
- Systemd integration
- Pod support (like Kubernetes)
- Docker-compatible CLI

## Installation

```bash
# Ubuntu/Debian
sudo apt install podman

# Fedora/RHEL
sudo dnf install podman

# Alias for Docker users
alias docker=podman
```

## Basic Commands

```bash
# Same as Docker
podman run -d nginx
podman ps
podman images
podman pull alpine
podman build -t myapp .
podman stop container_name
podman rm container_name

# Rootless by default
podman run -d -p 8080:80 nginx
```

## Pods

```bash
# Create pod
podman pod create --name mypod -p 8080:80

# Add containers to pod
podman run -d --pod mypod nginx
podman run -d --pod mypod redis

# List pods
podman pod ls

# Pod operations
podman pod start mypod
podman pod stop mypod
podman pod rm mypod

# Generate Kubernetes YAML
podman generate kube mypod > pod.yaml
```

## Systemd Integration

```bash
# Generate systemd unit file
podman generate systemd --name container_name > container.service

# Install as user service
mkdir -p ~/.config/systemd/user/
podman generate systemd --name myapp --files --new
mv container-myapp.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now container-myapp

# Install as system service (root)
sudo podman generate systemd --name myapp --files --new
sudo mv container-myapp.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now container-myapp
```

## Quadlet (Podman 4.4+)

```ini
# ~/.config/containers/systemd/myapp.container
[Container]
Image=docker.io/library/nginx:alpine
PublishPort=8080:80
Volume=./html:/usr/share/nginx/html:Z

[Service]
Restart=always

[Install]
WantedBy=default.target
```

```bash
# Reload and start
systemctl --user daemon-reload
systemctl --user start myapp
```

## Rootless Configuration

```bash
# Check user namespace
podman unshare cat /proc/self/uid_map

# Configure subordinate IDs
# /etc/subuid
username:100000:65536

# /etc/subgid
username:100000:65536

# Reset storage
podman system reset
```

## Docker Compatibility

```bash
# Enable Docker socket
systemctl --user enable --now podman.socket

# Use Docker CLI
export DOCKER_HOST=unix://$XDG_RUNTIME_DIR/podman/podman.sock
docker ps

# Docker Compose
podman-compose up -d
# Or use docker-compose with socket
```

## Image Management

```bash
# Registries config
# ~/.config/containers/registries.conf
[registries.search]
registries = ['docker.io', 'quay.io']

# Login to registry
podman login docker.io
podman login --get-login docker.io

# Push image
podman tag myapp docker.io/username/myapp
podman push docker.io/username/myapp
```
"""
        return ScrapedDocument(
            id=self._generate_id("podman-guide"),
            url="https://podman.io/docs",
            title="Podman Guide",
            content=content,
            source=self.get_source_name(),
            category="containers",
            tags=["podman", "containers", "linux", "rootless"],
            scraped_at=datetime.utcnow().isoformat(),
            metadata={"type": "guide", "priority": "high"}
        )
    
    def _container_networking_guide(self) -> ScrapedDocument:
        """Container networking guide."""
        content = """# Container Networking Guide

## Docker Network Types

```bash
# List networks
docker network ls

# Create network
docker network create mynetwork
docker network create --driver bridge mynetwork
docker network create --driver overlay mynetwork  # Swarm

# Inspect network
docker network inspect bridge

# Remove network
docker network rm mynetwork
docker network prune                   # Remove unused
```

## Network Drivers

### Bridge (Default)
```bash
# Default bridge (docker0)
docker run -d nginx                    # Uses default bridge

# Custom bridge
docker network create --driver bridge mybridge
docker run -d --network mybridge nginx

# Containers on same custom bridge can resolve by name
docker run -d --name web --network mybridge nginx
docker run -it --network mybridge alpine ping web
```

### Host
```bash
# Share host network (no isolation)
docker run -d --network host nginx
# Nginx listens on host port 80 directly
```

### None
```bash
# No networking
docker run -d --network none nginx
```

### Macvlan
```bash
# Container gets IP on physical network
docker network create -d macvlan \\
    --subnet=192.168.1.0/24 \\
    --gateway=192.168.1.1 \\
    -o parent=eth0 \\
    macvlan_net

docker run -d --network macvlan_net \\
    --ip 192.168.1.100 nginx
```

## Container DNS

```bash
# Custom DNS
docker run --dns 8.8.8.8 nginx

# Custom hostname
docker run --hostname myhost nginx

# Add hosts entry
docker run --add-host myhost:192.168.1.100 nginx

# Disable default DNS
docker run --dns-opt ndots:1 nginx
```

## Connecting Containers

```bash
# Connect to network
docker network connect mynetwork container_name

# Disconnect from network
docker network disconnect mynetwork container_name

# Run with multiple networks
docker run -d --network net1 --network net2 nginx
```

## Port Publishing

```bash
# Publish port
docker run -p 8080:80 nginx            # Host:Container
docker run -p 80 nginx                 # Random host port
docker run -P nginx                    # All exposed ports
docker run -p 127.0.0.1:8080:80 nginx  # Localhost only
docker run -p 8080:80/tcp nginx        # TCP only
docker run -p 8080:80/udp nginx        # UDP only

# Check published ports
docker port container_name
```

## Docker Compose Networking

```yaml
version: '3.8'

services:
  web:
    image: nginx
    networks:
      - frontend
    ports:
      - "80:80"
      
  api:
    build: ./api
    networks:
      - frontend
      - backend
      
  db:
    image: postgres
    networks:
      - backend

networks:
  frontend:
    driver: bridge
  backend:
    driver: bridge
    internal: true              # No external access
```

## Troubleshooting

```bash
# Check container IP
docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' container

# Test connectivity
docker exec container1 ping container2
docker exec container curl -I http://container2

# Check iptables rules
sudo iptables -L -n -t nat

# DNS resolution
docker exec container nslookup other_container
docker exec container cat /etc/resolv.conf
```
"""
        return ScrapedDocument(
            id=self._generate_id("container-networking"),
            url="https://docs.docker.com/network/",
            title="Container Networking Guide",
            content=content,
            source=self.get_source_name(),
            category="containers",
            tags=["docker", "containers", "networking", "linux"],
            scraped_at=datetime.utcnow().isoformat(),
            metadata={"type": "guide", "priority": "high"}
        )
    
    def _container_volumes_guide(self) -> ScrapedDocument:
        """Container volumes guide."""
        content = """# Container Volumes Guide

## Volume Types

### Named Volumes
```bash
# Create volume
docker volume create myvolume

# List volumes
docker volume ls

# Inspect volume
docker volume inspect myvolume

# Remove volume
docker volume rm myvolume
docker volume prune                    # Remove unused

# Use volume
docker run -v myvolume:/app/data nginx
docker run --mount source=myvolume,target=/app/data nginx
```

### Bind Mounts
```bash
# Mount host directory
docker run -v /host/path:/container/path nginx
docker run -v $(pwd)/data:/app/data nginx

# Mount syntax
docker run --mount type=bind,source=/host/path,target=/container/path nginx

# Read-only mount
docker run -v /host/path:/container/path:ro nginx
```

### tmpfs Mounts
```bash
# Mount tmpfs (in memory)
docker run --tmpfs /app/cache nginx
docker run --mount type=tmpfs,target=/app/cache nginx

# With options
docker run --mount type=tmpfs,target=/app/cache,tmpfs-size=100m nginx
```

## Volume Options

```bash
# Read-only
docker run -v myvolume:/data:ro nginx

# SELinux labels
docker run -v /host:/container:z nginx    # Shared
docker run -v /host:/container:Z nginx    # Private

# Nocopy (don't copy container data)
docker run -v myvolume:/data:nocopy nginx
```

## Docker Compose Volumes

```yaml
version: '3.8'

services:
  app:
    image: myapp
    volumes:
      # Named volume
      - app_data:/app/data
      # Bind mount
      - ./config:/app/config:ro
      # Anonymous volume
      - /app/cache
      # tmpfs
      - type: tmpfs
        target: /app/tmp

  db:
    image: postgres
    volumes:
      - db_data:/var/lib/postgresql/data

volumes:
  app_data:
  db_data:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: /data/postgres
```

## Backup and Restore

```bash
# Backup volume
docker run --rm -v myvolume:/source -v $(pwd):/backup alpine \\
    tar czf /backup/backup.tar.gz -C /source .

# Restore volume
docker run --rm -v myvolume:/target -v $(pwd):/backup alpine \\
    tar xzf /backup/backup.tar.gz -C /target

# Copy from container
docker cp container:/path/data ./backup/
```

## Volume Drivers

```bash
# Local driver (default)
docker volume create --driver local myvolume

# NFS volume
docker volume create --driver local \\
    --opt type=nfs \\
    --opt o=addr=192.168.1.100,rw \\
    --opt device=:/path/to/share \\
    nfs_volume

# CIFS/SMB volume
docker volume create --driver local \\
    --opt type=cifs \\
    --opt o=addr=192.168.1.100,username=user,password=pass \\
    --opt device=//192.168.1.100/share \\
    cifs_volume
```

## Permissions

```bash
# Container user permissions
docker run -u 1000:1000 -v $(pwd)/data:/data myapp

# Fix ownership in Dockerfile
RUN chown -R appuser:appuser /app/data

# Use numeric UID/GID
docker run -v $(pwd)/data:/data -u $(id -u):$(id -g) myapp
```
"""
        return ScrapedDocument(
            id=self._generate_id("container-volumes"),
            url="https://docs.docker.com/storage/",
            title="Container Volumes Guide",
            content=content,
            source=self.get_source_name(),
            category="containers",
            tags=["docker", "containers", "volumes", "storage"],
            scraped_at=datetime.utcnow().isoformat(),
            metadata={"type": "guide", "priority": "high"}
        )
    
    def _container_security_guide(self) -> ScrapedDocument:
        """Container security guide."""
        content = """# Container Security Guide

## Run as Non-Root

```dockerfile
# Dockerfile
FROM node:18-alpine
RUN addgroup -g 1001 appgroup && \\
    adduser -u 1001 -G appgroup -D appuser
USER appuser
WORKDIR /home/appuser/app
```

```bash
# Run as specific user
docker run -u 1000:1000 nginx
docker run --user nobody nginx
```

## Read-Only Filesystem

```bash
# Read-only root filesystem
docker run --read-only nginx

# With writable temp directory
docker run --read-only --tmpfs /tmp nginx

# Docker Compose
services:
  app:
    read_only: true
    tmpfs:
      - /tmp
```

## Capabilities

```bash
# Drop all capabilities
docker run --cap-drop=all nginx

# Add specific capability
docker run --cap-drop=all --cap-add=NET_BIND_SERVICE nginx

# Common capabilities to drop
docker run --cap-drop=SETUID --cap-drop=SETGID nginx
docker run --cap-drop=NET_RAW nginx
```

## Security Options

```bash
# No new privileges
docker run --security-opt=no-new-privileges nginx

# Seccomp profile
docker run --security-opt seccomp=profile.json nginx

# AppArmor profile
docker run --security-opt apparmor=docker-default nginx

# SELinux
docker run --security-opt label=type:container_t nginx
```

## Resource Limits

```bash
# Memory limits
docker run -m 512m nginx                   # Hard limit
docker run --memory-reservation=256m nginx # Soft limit
docker run --memory-swap=1g nginx          # Swap limit

# CPU limits
docker run --cpus=0.5 nginx                # 50% of one CPU
docker run --cpu-shares=512 nginx          # Relative weight
docker run --cpuset-cpus=0,1 nginx         # Specific CPUs

# PIDs limit
docker run --pids-limit=100 nginx
```

## Network Security

```bash
# Disable inter-container communication
docker network create --opt com.docker.network.bridge.enable_icc=false secure_net

# No network
docker run --network none nginx

# Read-only /etc/hosts
docker run --read-only nginx
```

## Image Security

```bash
# Scan for vulnerabilities
docker scan myimage
trivy image myimage

# Sign images (Docker Content Trust)
export DOCKER_CONTENT_TRUST=1
docker push myregistry/myimage

# Use digest instead of tag
docker pull nginx@sha256:abc123...
```

## Secrets Management

```bash
# Docker secrets (Swarm)
echo "mypassword" | docker secret create db_password -
docker service create --secret db_password myapp

# Docker Compose secrets
services:
  app:
    secrets:
      - db_password
secrets:
  db_password:
    file: ./secrets/db_password.txt
```

## Security Checklist

```markdown
- [ ] Run as non-root user
- [ ] Use read-only filesystem where possible
- [ ] Drop unnecessary capabilities
- [ ] Set memory and CPU limits
- [ ] Use no-new-privileges
- [ ] Scan images for vulnerabilities
- [ ] Use specific image tags (not :latest)
- [ ] Don't store secrets in images
- [ ] Use private registries
- [ ] Keep base images updated
- [ ] Use multi-stage builds
- [ ] Minimize installed packages
```

## Audit Containers

```bash
# Docker Bench Security
docker run -it --net host --pid host --userns host --cap-add audit_control \\
    -v /var/lib:/var/lib \\
    -v /var/run/docker.sock:/var/run/docker.sock \\
    docker/docker-bench-security
```
"""
        return ScrapedDocument(
            id=self._generate_id("container-security"),
            url="https://docs.docker.com/engine/security/",
            title="Container Security Guide",
            content=content,
            source=self.get_source_name(),
            category="security",
            tags=["docker", "containers", "security", "hardening"],
            scraped_at=datetime.utcnow().isoformat(),
            metadata={"type": "guide", "priority": "high"}
        )
    
    def _troubleshooting_guide(self) -> ScrapedDocument:
        """Container troubleshooting guide."""
        content = """# Container Troubleshooting Guide

## Container Won't Start

```bash
# Check logs
docker logs container_name
docker logs --tail 50 container_name

# Check events
docker events --since 10m

# Inspect container
docker inspect container_name

# Check exit code
docker inspect -f '{{.State.ExitCode}}' container_name

# Start with shell to debug
docker run -it --entrypoint /bin/sh image_name
```

## Debugging Running Container

```bash
# Execute shell
docker exec -it container_name /bin/bash
docker exec -it container_name /bin/sh

# Run as root
docker exec -u root -it container_name bash

# Check processes
docker top container_name
docker exec container_name ps aux

# Check network
docker exec container_name netstat -tlnp
docker exec container_name ss -tlnp
docker exec container_name cat /etc/resolv.conf
```

## Network Issues

```bash
# Check container IP
docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' container_name

# Check port mapping
docker port container_name

# Test connectivity
docker exec container_name ping google.com
docker exec container_name curl -I http://other_container

# Check DNS resolution
docker exec container_name nslookup other_container

# Inspect network
docker network inspect bridge
```

## Storage Issues

```bash
# Check disk usage
docker system df
docker system df -v

# Find large containers
docker ps --size

# Check volume
docker volume inspect volume_name

# Clean up
docker system prune
docker volume prune
docker image prune -a
```

## Performance Issues

```bash
# Resource usage
docker stats
docker stats container_name

# Top processes in container
docker top container_name

# Check limits
docker inspect -f '{{.HostConfig.Memory}}' container_name
docker inspect -f '{{.HostConfig.NanoCpus}}' container_name
```

## Image Issues

```bash
# Build failures
docker build --no-cache -t myapp .
docker build --progress=plain -t myapp .

# Check layers
docker history image_name
docker inspect image_name

# Pull issues
docker pull --disable-content-trust image_name
```

## Common Errors

### "Permission denied"
```bash
# Check user
docker exec container_name whoami

# Fix ownership
docker exec -u root container_name chown -R appuser:appuser /app

# SELinux (add :Z or :z)
docker run -v /host:/container:Z image_name
```

### "Port already in use"
```bash
# Find what's using the port
sudo lsof -i :8080
sudo ss -tlnp | grep 8080

# Use different port
docker run -p 8081:80 nginx
```

### "No space left on device"
```bash
# Clean up
docker system prune -a --volumes

# Check overlay2 usage
du -sh /var/lib/docker/overlay2/*
```

### "Container keeps restarting"
```bash
# Check restart policy
docker inspect -f '{{.HostConfig.RestartPolicy}}' container_name

# View logs
docker logs -f container_name

# Stop restart loop
docker update --restart=no container_name
```

## Docker Daemon Issues

```bash
# Check daemon status
sudo systemctl status docker

# View daemon logs
sudo journalctl -u docker -f

# Restart daemon
sudo systemctl restart docker

# Check daemon config
cat /etc/docker/daemon.json
```
"""
        return ScrapedDocument(
            id=self._generate_id("container-troubleshooting"),
            url="synthetic://container-troubleshooting",
            title="Container Troubleshooting Guide",
            content=content,
            source=self.get_source_name(),
            category="troubleshooting",
            tags=["docker", "containers", "troubleshooting", "debugging"],
            scraped_at=datetime.utcnow().isoformat(),
            metadata={"type": "troubleshooting", "priority": "high"}
        )
    
    def _generate_id(self, name: str) -> str:
        """Generate document ID."""
        import hashlib
        return hashlib.md5(f"containers-docs:{name}".encode()).hexdigest()[:16]


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Generate container documentation")
    parser.add_argument("--output-dir", default="data/linux/containers-docs")
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(name)s:%(message)s')
    
    config = ScraperConfig(output_dir=Path(args.output_dir))
    scraper = ContainersDocsScraper(config)
    
    docs = scraper.scrape()
    scraper.save_documents(docs, "containers_docs.jsonl")
