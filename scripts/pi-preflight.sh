#!/bin/sh
# Read-only inventory. No daemon restart, installation or permission changes.
set -u
uname -m
cat /etc/os-release
free -h
df -h
command -v docker
command -v docker.compose || true
snap list docker
snap connections docker
sudo -n docker version
sudo -n docker ps --format '{{.Names}}\t{{.Image}}\t{{.Ports}}'
sudo -n docker stats --no-stream --format '{{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}'
sudo -n docker.compose version || sudo -n docker compose version
ss -ltn
