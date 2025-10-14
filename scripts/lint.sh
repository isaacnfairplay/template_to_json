#!/usr/bin/env bash
set -euo pipefail

uvx ruff check .
uvx mypy .
