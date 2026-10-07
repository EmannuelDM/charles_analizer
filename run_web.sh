#!/usr/bin/env bash
# ==============================================================================
# Charles Proxy Analyzer - Web Application Launcher
# ==============================================================================
# This script sets up the Python virtual environment, verifies dependencies,
# and starts the interactive Web Application.
#
# Usage:
#   ./run_web.sh                     # Start on default port 8000 & open browser
#   ./run_web.sh session.chlz        # Start and preload session file
#   ./run_web.sh --port 8080         # Start on port 8080
#   ./run_web.sh -p 9000             # Short form for port
#   ./run_web.sh --no-browser        # Start without auto-opening web browser
#   ./run_web.sh --reinstall         # Force reinstall dependencies
# ==============================================================================

set -eo pipefail

# ANSI color codes
BOLD="\033[1m"
GREEN="\033[0;32m"
BLUE="\033[0;34m"
YELLOW="\033[0;33m"
RED="\033[0;31m"
CYAN="\033[0;36m"
RESET="\033[0m"

# Navigate to project root directory
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

# Check if --help or -h was passed
for arg in "$@"; do
    if [ "$arg" == "--help" ] || [ "$arg" == "-h" ]; then
        if [ -f ".venv/bin/python" ]; then
            exec .venv/bin/python server.py --help
        elif command -v python3 &>/dev/null; then
            exec python3 server.py --help
        elif command -v python &>/dev/null; then
            exec python server.py --help
        fi
    fi
done

# Check if --reinstall was passed
FORCE_REINSTALL=0
PASSED_ARGS=()
for arg in "$@"; do
    if [ "$arg" == "--reinstall" ] || [ "$arg" == "--install" ]; then
        FORCE_REINSTALL=1
    else
        PASSED_ARGS+=("$arg")
    fi
done

echo -e "${BOLD}${CYAN}==============================================================================${RESET}"
echo -e "${BOLD}${CYAN}            Charles Proxy Analyzer - Web Application Launcher                 ${RESET}"
echo -e "${BOLD}${CYAN}==============================================================================${RESET}"

# 1. Detect Python 3
PYTHON_BIN=""
if command -v python3 &> /dev/null; then
    PYTHON_BIN="python3"
elif command -v python &> /dev/null; then
    # Verify if 'python' is Python 3
    if python -c 'import sys; exit(0 if sys.version_info[0] >= 3 else 1)' &> /dev/null; then
        PYTHON_BIN="python"
    fi
fi

if [ -z "$PYTHON_BIN" ]; then
    echo -e "${RED}[ERROR] Python 3 was not found on your system.${RESET}"
    echo "Please install Python 3.8 or higher to continue."
    exit 1
fi

PY_VER=$($PYTHON_BIN -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo -e "${BLUE}[INFO]${RESET} Using Python ${BOLD}${PY_VER}${RESET} (${PYTHON_BIN})"

# 2. Virtual Environment Setup
VENV_DIR=""
if [ -d ".venv" ]; then
    VENV_DIR=".venv"
elif [ -d "venv" ]; then
    VENV_DIR="venv"
fi

if [ -z "$VENV_DIR" ]; then
    echo -e "${BLUE}[INFO]${RESET} Creating virtual environment in ${BOLD}.venv${RESET}..."
    if $PYTHON_BIN -m venv .venv 2>/dev/null; then
        VENV_DIR=".venv"
        echo -e "${GREEN}[OK]${RESET} Virtual environment created."
    else
        echo -e "${YELLOW}[WARN]${RESET} Could not create virtual environment (python3-venv might be missing)."
        echo -e "${YELLOW}[WARN]${RESET} Continuing with system environment..."
    fi
fi

# Activate virtual environment if available
if [ -n "$VENV_DIR" ] && [ -f "$VENV_DIR/bin/activate" ]; then
    echo -e "${BLUE}[INFO]${RESET} Activating virtual environment (${VENV_DIR})..."
    # shellcheck disable=SC1090
    source "$VENV_DIR/bin/activate"
    ENV_PYTHON="$VENV_DIR/bin/python"
else
    ENV_PYTHON="$PYTHON_BIN"
fi

# 3. Check and Install Requirements
NEEDS_INSTALL=$FORCE_REINSTALL
if [ "$NEEDS_INSTALL" -eq 0 ]; then
    # Check if optional brotli is already importable
    if ! "$ENV_PYTHON" -c "import brotli" &>/dev/null; then
        NEEDS_INSTALL=1
    fi
fi

if [ "$NEEDS_INSTALL" -eq 1 ]; then
    echo -e "${BLUE}[INFO]${RESET} Installing requirements..."
    if [ -f "requirements.txt" ]; then
        if "$ENV_PYTHON" -m pip install -r requirements.txt -q 2>/dev/null; then
            echo -e "${GREEN}[OK]${RESET} Requirements satisfied (from requirements.txt)."
        else
            "$ENV_PYTHON" -m pip install -r requirements.txt --break-system-packages -q 2>/dev/null || {
                echo -e "${YELLOW}[WARN]${RESET} pip install warning. Attempting to proceed..."
            }
        fi
    fi

    # Install package in editable mode if pyproject.toml / setup.py exists
    if [ -f "setup.py" ] || [ -f "pyproject.toml" ]; then
        "$ENV_PYTHON" -m pip install -e . --no-deps -q 2>/dev/null || true
    fi
else
    echo -e "${GREEN}[OK]${RESET} Dependencies already satisfied (brotli ready)."
fi

# 4. Launch the Web Application
echo -e "${GREEN}${BOLD}[LAUNCH]${RESET} Starting Web Application Server..."
echo -e "${CYAN}------------------------------------------------------------------------------${RESET}"

# Forward arguments to server.py
exec "$ENV_PYTHON" server.py "${PASSED_ARGS[@]}"
