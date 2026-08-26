# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Halbert Dashboard Entry Point

Run the dashboard server with:
    python -m halbert_core.dashboard

Options:
    --port PORT     Port to run on (default: $HALBERT_PORT or 8000)
    --host HOST     Host to bind to (default: $HALBERT_HOST or 127.0.0.1)
    --reload        Enable auto-reload for development
"""

import argparse
import logging
import os
import socket
import sys

# Configure logging before imports
logging.basicConfig(
    level=logging.INFO,
    format='{"ts": "%(asctime)s", "level": "%(levelname)s", "logger": "%(name)s", "msg": "%(message)s"}',
    datefmt='%Y-%m-%dT%H:%M:%S%z'
)

logger = logging.getLogger('halbert.main')


def find_available_port(start: int = 8000, end: int = 8100) -> int:
    """Find an available port in the given range."""
    for port in range(start, end):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('127.0.0.1', port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"No available ports in range {start}-{end}")


def check_ollama() -> tuple[bool, str]:
    """Check if Ollama is installed and running."""
    import subprocess
    
    # Check if installed
    try:
        result = subprocess.run(['ollama', '--version'], capture_output=True, timeout=5)
        if result.returncode != 0:
            return False, "Ollama not installed. Install with: curl -fsSL https://ollama.com/install.sh | sh"
    except FileNotFoundError:
        return False, "Ollama not installed. Install with: curl -fsSL https://ollama.com/install.sh | sh"
    except subprocess.TimeoutExpired:
        return False, "Ollama check timed out"
    
    # Check if running
    try:
        import requests
        r = requests.get('http://localhost:11434/api/tags', timeout=2)
        if r.status_code == 200:
            return True, "Ollama ready"
    except Exception:
        pass
    
    # Try to start Ollama
    logger.info("Ollama not running, attempting to start...")
    try:
        subprocess.Popen(
            ['ollama', 'serve'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )
        import time
        time.sleep(3)
        
        # Check again
        try:
            import requests
            r = requests.get('http://localhost:11434/api/tags', timeout=2)
            if r.status_code == 200:
                return True, "Ollama started successfully"
        except Exception:
            pass
    except Exception as e:
        logger.warning(f"Failed to start Ollama: {e}")
    
    return False, "Ollama installed but not running. Start with: ollama serve"


def main():
    parser = argparse.ArgumentParser(
        description='Halbert AI Assistant Dashboard Server',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python -m halbert_core.dashboard
    python -m halbert_core.dashboard --port 8080
    python -m halbert_core.dashboard --reload
        """
    )
    parser.add_argument('--port', type=int, default=int(os.environ.get('HALBERT_PORT', 8000)),
                        help='Port to run on (default: $HALBERT_PORT or 8000)')
    parser.add_argument('--host', type=str, default=os.environ.get('HALBERT_HOST', '127.0.0.1'),
                        help='Host to bind to (default: $HALBERT_HOST or 127.0.0.1)')
    parser.add_argument('--reload', action='store_true', help='Enable auto-reload for development')
    parser.add_argument('--no-ollama-check', action='store_true', help='Skip Ollama availability check')
    parser.add_argument('--find-port', action='store_true', help='Automatically find available port')
    
    args = parser.parse_args()
    
    # Check Ollama
    if not args.no_ollama_check:
        ollama_ok, ollama_msg = check_ollama()
        if ollama_ok:
            logger.info(f"✓ {ollama_msg}")
        else:
            logger.warning(f"⚠ {ollama_msg}")
            logger.warning("Halbert will run but LLM features will be unavailable")
    
    # Find available port if requested or if default port is busy
    port = args.port
    if args.find_port:
        try:
            port = find_available_port(args.port, args.port + 100)
            if port != args.port:
                logger.info(f"Port {args.port} busy, using port {port}")
        except RuntimeError as e:
            logger.error(str(e))
            sys.exit(1)
    
    # Import and create app
    try:
        from .app import create_app
    except ImportError:
        from halbert_core.dashboard.app import create_app
    
    app = create_app(enable_cors=True)
    
    # Start server
    logger.info(f"Starting Halbert Dashboard on http://{args.host}:{port}")
    
    try:
        import uvicorn
        if args.reload:
            # uvicorn requires an import string (not an app object) for reload
            uvicorn.run(
                "halbert_core.dashboard.app:app",
                host=args.host,
                port=port,
                reload=True,
                log_level="info"
            )
        else:
            uvicorn.run(app, host=args.host, port=port, log_level="info")
    except ImportError:
        logger.error("uvicorn not installed. Install with: pip install uvicorn[standard]")
        sys.exit(1)


if __name__ == "__main__":
    main()
