"""PWSSAP Standalone Windows/Web Application Launcher.

Starts the FastAPI server (which serves both the API and the React frontend SPA)
and automatically launches the application in a standalone desktop window (via Edge/Chrome App Mode)
or in the default web browser.
"""
import os
import sys
import time
import subprocess
import threading
import urllib.request
import webbrowser

# Ensure backend directory is in sys.path
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.join(ROOT_DIR, "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

HOST = "127.0.0.1"
PORT = 8000
APP_URL = f"http://{HOST}:{PORT}"
HEALTH_URL = f"http://{HOST}:{PORT}/health"


def wait_for_server(url: str, timeout: float = 15.0) -> bool:
    """Poll the server until it returns HTTP 200 or timeout expires."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            with urllib.request.urlopen(url, timeout=1.0) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            time.sleep(0.3)
    return False


def launch_browser(url: str) -> None:
    """Open the application in desktop app mode if available, else default browser."""
    if not wait_for_server(HEALTH_URL):
        print("  [!] Warning: Server is taking longer than usual to respond. Opening browser anyway...")

    # Look for Microsoft Edge (installed by default on all Windows 10/11 machines)
    edge_candidates = [
        os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%LocalAppData%\Microsoft\Edge\Application\msedge.exe"),
    ]
    for exe in edge_candidates:
        if os.path.isfile(exe):
            try:
                subprocess.Popen([exe, f"--app={url}"])
                return
            except Exception:
                pass

    # Look for Google Chrome
    chrome_candidates = [
        os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
    ]
    for exe in chrome_candidates:
        if os.path.isfile(exe):
            try:
                subprocess.Popen([exe, f"--app={url}"])
                return
            except Exception:
                pass

    # Fallback to system default web browser
    webbrowser.open(url)


def print_banner():
    banner = f"""
======================================================================
     PWSSAP - Course Timetable Management & Scheduling System         
======================================================================

  * Server status:  Running locally
  * Web Address:    {APP_URL}
  
  QUICK START GUIDE:
  ------------------------------------------------------------------
  1. Welcome Screen: Type "admin" to log in as Timetable Coordinator.
  2. Traditional Mode: Click "Classes & Batches (Traditional)" in the
     sidebar to manage divisions, lab batches, and fixed sections.
  3. Solver: Go to "Solver" to run timetable generation and view reports.
  4. Data: Sample files are located in the "demo_run" folder.

  TO STOP THE SERVER:
  Press Ctrl + C in this terminal window, or simply close this window.
======================================================================
"""
    print(banner)


def main():
    import uvicorn
    from main import app

    print("\n[*] Initializing PWSSAP backend and user interface...")

    # Launch browser window in background thread once server starts
    browser_thread = threading.Thread(target=launch_browser, args=(APP_URL,), daemon=True)
    browser_thread.start()

    print_banner()

    # Run Uvicorn server
    config = uvicorn.Config(
        app=app,
        host=HOST,
        port=PORT,
        log_level="warning",
        access_log=False
    )
    server = uvicorn.Server(config)
    try:
        server.run()
    except (KeyboardInterrupt, SystemExit):
        print("\n[*] PWSSAP Server stopped cleanly. Goodbye!")


if __name__ == "__main__":
    main()
