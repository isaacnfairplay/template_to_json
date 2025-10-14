#!/usr/bin/env bash
set -euo pipefail

uvx ruff format "$@"
