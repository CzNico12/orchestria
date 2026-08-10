#!/bin/bash
cd "$(dirname "$0")"
.venv/bin/uvicorn server:app --host 127.0.0.1 --port 5151