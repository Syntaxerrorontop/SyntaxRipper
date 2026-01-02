"""
Universal Web Scraper - A comprehensive scraping class that handles everything:
- Cloudflare challenges automatically
- HTML extraction and parsing
- Element clicking and interaction
- Asset downloading (images, files, etc.)
- Session persistence across requests
- Advanced anti-detection measures
"""

import os
import time
import logging
import platform
import re
import threading
import queue
import uuid
import signal
import atexit
from typing import Optional, Dict, Any, List, Union, Callable
from urllib.parse import urljoin, urlparse
from concurrent.futures import Future
import requests
from pathlib import Path

# Windows API for hiding windows
if platform.system() == "Windows":
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

# Global registry to track active Chrome processes for cleanup
_active_chrome_processes = set()
_cleanup_lock = threading.Lock()


def _emergency_cleanup():
    """Emergency cleanup function called on program exit"""
    with _cleanup_lock:
        if _active_chrome_processes:
            logging.info("\n🚨 Emergency cleanup: Terminating Chrome processes...")
            for pid in list(_active_chrome_processes):
                try:
                    process = psutil.Process(pid)
                    if process.is_running():
                        # Kill Chrome process tree
                        children = process.children(recursive=True)
                        for child in children:
                            try:
                                child.terminate()
                            except psutil.NoSuchProcess:
                                pass

                        process.terminate()
                        # Wait a bit, then force kill if still alive
                        try:
                            process.wait(timeout=3)
                        except psutil.TimeoutExpired:
                            process.kill()

                        logging.info(f"✅ Terminated Chrome process {pid}")
                except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                    pass
            _active_chrome_processes.clear()
            logging.info("🧹 Emergency cleanup completed")


# Register emergency cleanup
atexit.register(_emergency_cleanup)

# Install dependencies if needed
try:
    import undetected_chromedriver as uc
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.common.action_chains import ActionChains
    from selenium.webdriver.support.wait import WebDriverWait
    from selenium.webdriver.support.expected_conditions import (
        presence_of_element_located,
        title_is,
        staleness_of,
        element_to_be_clickable,
    )
    from selenium.common import TimeoutException, NoSuchElementException
    from bs4 import BeautifulSoup
    import colorama
    import psutil
except ImportError:
    logging.info("Installing required dependencies...")
    import subprocess

    subprocess.check_call(
        [
            "pip",
            "install",
            "setuptools",
            "undetected-chromedriver",
            "selenium",
            "beautifulsoup4",
            "requests",
            "colorama",
            "psutil",
        ]
    )
    import undetected_chromedriver as uc
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.common.action_chains import ActionChains
    from selenium.webdriver.support.wait import WebDriverWait
    from selenium.webdriver.support.expected_conditions import (
        presence_of_element_located,
        title_is,
        staleness_of,
        element_to_be_clickable,
    )
    from selenium.common import TimeoutException, NoSuchElementException
    from bs4 import BeautifulSoup
    import psutil

# Challenge detection patterns
CHALLENGE_TITLES = ["Just a moment...", "DDoS-Guard", "Please verify you are human"]
CHALLENGE_SELECTORS = [
    # Cloudflare
    "#cf-challenge-running",
    ".ray_id",
    ".attack-box",
    "#cf-please-wait",
    "#challenge-spinner",
    "#trk_jschal_js",
    "#turnstile-wrapper",
    ".lds-ring",
    "td.info #js_info",
    "div.vc div.text-box h2",
    # reCAPTCHA
    ".g-recaptcha",
    "[data-sitekey]",
    ".recaptcha-checkbox",
    'iframe[src*="recaptcha"]',
    # hCaptcha
    ".h-captcha",
    "[data-hcaptcha-sitekey]",
    'iframe[src*="hcaptcha"]',
    # Cloudflare Turnstile
    ".cf-turnstile",
    "[data-cf-turnstile-sitekey]",
]

# CAPTCHA specific selectors
CAPTCHA_SELECTORS = {
    "recaptcha_v2": {
        "checkbox": ".recaptcha-checkbox-border",
        "iframe": 'iframe[src*="recaptcha"]',
        "challenge_frame": 'iframe[src*="recaptcha"][src*="bframe"]',
    },
    "hcaptcha": {"checkbox": ".hcaptcha-checkbox", "iframe": 'iframe[src*="hcaptcha"]'},
    "turnstile": {"widget": ".cf-turnstile", "checkbox": ".cf-turnstile-wrapper"},
}


class ScraperOperation:
    """
    Represents a single operation to be executed by the scraper
    """

    def __init__(self, operation_id: str, method_name: str, args: tuple, kwargs: dict):
        self.operation_id = operation_id
        self.method_name = method_name
        self.args = args
        self.kwargs = kwargs
        self.result_future = Future()
        self.created_at = time.time()
        self.started_at = None
        self.completed_at = None
        self.thread_name = threading.current_thread().name

    def __str__(self):
        return f"Operation[{self.operation_id[:8]}]: {self.method_name}({self.args}, {self.kwargs})"

    def set_result(self, result):
        """Set the operation result"""
        self.completed_at = time.time()
        self.result_future.set_result(result)

    def set_exception(self, exception):
        """Set an exception result"""
        self.completed_at = time.time()
        self.result_future.set_exception(exception)

    def get_result(self, timeout=None):
        """Get the operation result (blocks until complete)"""
        return self.result_future.result(timeout=timeout)

    def get_execution_time(self):
        """Get the total execution time"""
        if self.started_at and self.completed_at:
            return self.completed_at - self.started_at
        return None

    def get_wait_time(self):
        """Get the time spent waiting in queue"""
        if self.started_at:
            return self.started_at - self.created_at
        return time.time() - self.created_at


class UniversalScraper:
    """
    A comprehensive web scraper that handles Cloudflare challenges,
    HTML extraction, clicking, and asset downloading.
    """

    def __init__(
        self,
        headless: bool = True,
        timeout: int = 30,
        download_dir: str = ".",
        hide_window: bool = True,
    ):
        """
        Initialize the Universal Scraper

        Args:
            headless: Run browser in headless mode (deprecated - use hide_window instead)
            timeout: Default timeout for operations
            download_dir: Directory to save downloaded files
            hide_window: Hide browser window using psutil (recommended over headless)
        """
        self.driver = None
        self.headless = headless
        self.hide_window = hide_window
        self.timeout = timeout
        self.download_dir = Path(download_dir)
        self.download_dir.mkdir(exist_ok=True)
        self.user_agent = None
        self.current_url = None
        self.session = requests.Session()
        self.chrome_process = None  # Store Chrome process for window hiding
        self.chrome_pids = set()  # Track Chrome process IDs for cleanup
        self.my_chrome_pids = set()  # Track PIDs specific to this scraper instance

        self.logger = logging.getLogger("UniversalScraper")

        # Set log level based on headless mode (less verbose when headless)
        if headless:
            self.logger.setLevel(logging.INFO)
        else:
            self.logger.setLevel(logging.DEBUG)

        # Register signal handlers for graceful shutdown
        self._setup_signal_handlers()

        # Thread-safe operation queue system
        self.operation_queue = queue.Queue(
            maxsize=100
        )  # Prevent unlimited queue growth
        self.queue_worker_thread = None
        self.queue_running = False
        self.queue_lock = threading.RLock()
        self.operation_stats = {
            "total_operations": 0,
            "completed_operations": 0,
            "failed_operations": 0,
            "queue_size": 0,
        }

        # Thread safety validation
        self._validate_thread_safety()

        self.logger.info(f"UniversalScraper initialized with queue system")

        # Log window hiding setting
        if self.hide_window and platform.system() == "Windows":
            self.logger.info("Window hiding enabled - Chrome will be invisible")
        elif self.headless:
            self.logger.info("Headless mode enabled")

    def _hide_chrome_windows(self) -> None:
        """Hide all Chrome windows associated with this scraper instance using Windows API"""

        if platform.system() != "Windows":

            self.logger.warning("Window hiding only supported on Windows")

            return

        try:

            # Find Chrome windows and hide them

            windows = []  # Move outside callback

            def enum_windows_callback(hwnd, lparam):

                if user32.IsWindowVisible(hwnd):

                    try:

                        # Get process ID for this window

                        process_id = wintypes.DWORD()

                        user32.GetWindowThreadProcessId(
                            hwnd, ctypes.byref(process_id)
                        )

                        pid = process_id.value

                        # Check if this PID belongs to our scraper instance

                        if pid in self.my_chrome_pids:

                            # Get window title for logging

                            length = user32.GetWindowTextLengthW(hwnd)

                            title = "Untitled"

                            if length > 0:

                                title_buffer = ctypes.create_unicode_buffer(
                                    length + 1
                                )

                                user32.GetWindowTextW(
                                    hwnd, title_buffer, length + 1
                                )

                                title = title_buffer.value

                            self.logger.debug(
                                f"Hiding Chrome window: {title} (PID: {pid})"
                            )

                            user32.ShowWindow(hwnd, 0)  # SW_HIDE = 0

                            windows.append(hwnd)

                    except Exception:

                        # Skip this window if we can't get process info

                        pass

                return True

            # Enumerate all windows

            WNDENUMPROC = ctypes.WINFUNCTYPE(
                wintypes.BOOL, wintypes.HWND, wintypes.LPARAM
            )

            user32.EnumWindows(WNDENUMPROC(enum_windows_callback), 0)

            if windows:

                self.logger.info(f"Hidden {len(windows)} Chrome windows")

            # else:
            #    self.logger.debug("No Chrome windows found to hide")

        except Exception as e:

            self.logger.error(f"Error hiding Chrome windows: {e}")

    def _find_chrome_process(self) -> Optional[psutil.Process]:
        """Find the Chrome process associated with our webdriver"""

        try:

            if not self.driver:

                return None

            # Return the first PID from our tracked list if available

            if self.my_chrome_pids:

                pid = next(iter(self.my_chrome_pids))

                return psutil.Process(pid)

        except Exception as e:

            self.logger.debug(f"Could not find Chrome process: {e}")

        return None

    def _setup_signal_handlers(self) -> None:
        """Setup signal handlers for graceful shutdown"""

        def signal_handler(signum, frame):

            self.logger.info(f"Received signal {signum}, cleaning up...")

            self.close()

            exit(0)

        try:

            # Register handlers for common termination signals

            if platform.system() != "Windows":

                signal.signal(signal.SIGTERM, signal_handler)

                signal.signal(signal.SIGINT, signal_handler)

            else:

                # Windows doesn't support SIGTERM, use SIGINT (Ctrl+C)

                signal.signal(signal.SIGINT, signal_handler)

        except ValueError:

            self.logger.debug(
                "Could not register signal handlers (not in main thread)"
            )

    def _register_chrome_process(self, process: psutil.Process) -> None:
        """Register a Chrome process for cleanup tracking"""

        if process and process.is_running():

            with _cleanup_lock:

                self.chrome_pids.add(process.pid)

                _active_chrome_processes.add(process.pid)

                self.logger.debug(
                    f"Registered Chrome process {process.pid} for cleanup"
                )

    def _unregister_chrome_process(self, pid: int) -> None:
        """Unregister a Chrome process from cleanup tracking"""

        with _cleanup_lock:

            self.chrome_pids.discard(pid)

            _active_chrome_processes.discard(pid)

            self.logger.debug(f"Unregistered Chrome process {pid} from cleanup")

    def _kill_chrome_processes(self) -> None:
        """Forcefully kill all tracked Chrome processes"""

        killed_count = 0

        with _cleanup_lock:

            # Combine manually tracked Pids and discovered ones

            all_pids = self.chrome_pids.union(self.my_chrome_pids)

            for pid in list(all_pids):

                try:

                    process = psutil.Process(pid)

                    if process.is_running():

                        self.logger.info(f"Terminating Chrome process {pid}...")

                        # Kill all children first

                        try:

                            children = process.children(recursive=True)

                            for child in children:

                                try:

                                    child.terminate()

                                    child.wait(timeout=1)

                                except (
                                    psutil.TimeoutExpired,
                                    psutil.NoSuchProcess,
                                ):

                                    try:

                                        child.kill()

                                    except psutil.NoSuchProcess:

                                        pass

                        except psutil.NoSuchProcess:

                            pass

                        # Now kill the main process

                        try:

                            process.terminate()

                            process.wait(timeout=3)

                        except psutil.TimeoutExpired:

                            self.logger.warning(
                                f"Force killing Chrome process {pid}"
                            )

                            process.kill()

                            process.wait(timeout=1)

                        killed_count += 1

                        self._unregister_chrome_process(pid)

                except (psutil.NoSuchProcess, psutil.AccessDenied) as e:

                    self._unregister_chrome_process(pid)

        if killed_count > 0:

            self.logger.info(
                f"Successfully terminated {killed_count} Chrome processes"
            )

    def _register_webdriver_chrome_processes(self) -> None:
        """Register Chrome processes spawned by webdriver for cleanup"""
        # This is now largely handled by the PID snapshot logic in _create_webdriver
        # But we keep it to catch any children spawned later
        try:
            if not self.my_chrome_pids:
                return

            # Scan for children of our known PIDs
            for pid in list(self.my_chrome_pids):
                try:
                    parent = psutil.Process(pid)
                    children = parent.children(recursive=True)
                    for child in children:
                        if child.pid not in self.my_chrome_pids:
                            self.my_chrome_pids.add(child.pid)
                            self._register_chrome_process(child)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

        except Exception as e:
            self.logger.debug(f"Error registering webdriver Chrome processes: {e}")

    def __enter__(self):
        """Context manager entry"""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close()

    def _validate_thread_safety(self) -> None:
        """Validate that the queue system provides proper thread safety"""
        # This method logs information about thread safety features
        self.logger.debug("🔒 Thread safety features enabled:")
        self.logger.debug("   - Queue-based operation serialization")
        self.logger.debug("   - RLock for critical sections")
        self.logger.debug("   - Operation result futures for thread coordination")
        self.logger.debug("   - Dedicated worker thread for sequential processing")

    def _start_queue_worker(self) -> None:
        """Start the queue worker thread"""
        with self.queue_lock:
            if not self.queue_running:
                self.queue_running = True
                self.queue_worker_thread = threading.Thread(
                    target=self._queue_worker, name="ScraperQueue", daemon=True
                )
                self.queue_worker_thread.start()
                self.logger.info("🔄 Queue worker thread started")

    def _stop_queue_worker(self) -> None:
        """Stop the queue worker thread"""
        with self.queue_lock:
            if self.queue_running:
                self.logger.info("🚫 Stopping queue worker thread...")
                self.queue_running = False

                # Add a sentinel value to wake up the worker
                try:
                    self.operation_queue.put(None, timeout=1)
                except queue.Full:
                    pass

                # Wait for worker thread to finish
                if self.queue_worker_thread and self.queue_worker_thread.is_alive():
                    self.queue_worker_thread.join(timeout=5)
                    if self.queue_worker_thread.is_alive():
                        self.logger.warning(
                            "⚠️ Queue worker thread did not stop gracefully"
                        )

                self.logger.info("✅ Queue worker stopped")

    def _queue_worker(self) -> None:
        """Main queue worker loop - processes operations sequentially"""
        self.logger.info("🛠️ Queue worker started, processing operations...")

        while self.queue_running:
            operation = None
            try:
                # Get next operation from queue (blocks until available)
                operation = self.operation_queue.get(timeout=1)

                # Sentinel value to stop worker
                if operation is None:
                    self.logger.debug("💭 Received stop signal, exiting queue worker")
                    break

                self._execute_operation(operation)

            except queue.Empty:
                # Timeout - continue loop to check if we should still be running
                continue
            except Exception as e:
                self.logger.error(f"🚫 Unexpected error in queue worker: {e}")
                if operation:
                    try:
                        operation.set_exception(e)
                    except:
                        pass
            finally:
                # Always mark task as done if we got an operation
                if operation is not None:
                    try:
                        self.operation_queue.task_done()
                    except ValueError:
                        # task_done() called too many times
                        pass

        self.logger.info("💭 Queue worker thread finished")

    def _execute_operation(self, operation: ScraperOperation) -> None:
        """Execute a single operation from the queue"""
        operation.started_at = time.time()

        with self.queue_lock:
            self.operation_stats["queue_size"] = self.operation_queue.qsize()

        wait_time = operation.get_wait_time()
        self.logger.debug(f"Executing {operation} (waited {wait_time:.3f}s)")

        try:
            # Get the actual method to call
            method_name = f"_internal_{operation.method_name}"
            if hasattr(self, method_name):
                method = getattr(self, method_name)
                result = method(*operation.args, **operation.kwargs)
                operation.set_result(result)

                with self.queue_lock:
                    self.operation_stats["completed_operations"] += 1

                exec_time = operation.get_execution_time()
                self.logger.debug(
                    f"Completed {operation.method_name} in {exec_time:.3f}s"
                )
            else:
                raise AttributeError(f"Method {method_name} not found")

        except Exception as e:
            self.logger.error(f"Error executing {operation}: {e}")
            operation.set_exception(e)

            with self.queue_lock:
                self.operation_stats["failed_operations"] += 1

    def _submit_operation(
        self,
        method_name: str, *args, timeout: int = None, **kwargs
    ) -> Any:
        """Submit an operation to the queue and wait for result"""
        operation_id = str(uuid.uuid4())
        operation = ScraperOperation(operation_id, method_name, args, kwargs)

        with self.queue_lock:
            self.operation_stats["total_operations"] += 1
            current_queue_size = self.operation_queue.qsize()

        thread_name = threading.current_thread().name
        if current_queue_size > 0:
            self.logger.debug(
                f"[{thread_name}] Queuing {method_name} (queue size: {current_queue_size})"
            )
        else:
            self.logger.debug(f"[{thread_name}] Executing {method_name} immediately")

        # Ensure worker is running
        self._start_queue_worker()

        # Add operation to queue
        try:
            self.operation_queue.put(
                operation, timeout=5
            )  # Prevent indefinite blocking
        except queue.Full:
            self.logger.error(f"Queue is full, cannot submit {method_name}")
            raise Exception(f"Queue is full, cannot submit operation: {method_name}")

        # Wait for result
        try:
            result = operation.get_result(timeout=timeout or self.timeout * 3)
            self.logger.debug(f"[{thread_name}] {method_name} completed successfully")
            return result
        except Exception as e:
            self.logger.error(
                f"[{thread_name}] Operation {method_name} failed or timed out: {e}"
            )
            raise

    def get_queue_stats(self) -> Dict[str, Any]:
        """Get current queue statistics"""
        with self.queue_lock:
            stats = self.operation_stats.copy()
            stats["queue_size"] = self.operation_queue.qsize()
            stats["queue_maxsize"] = self.operation_queue.maxsize
            stats["worker_running"] = self.queue_running
            stats["worker_alive"] = (
                self.queue_worker_thread and self.queue_worker_thread.is_alive()
            )
            stats["worker_thread_name"] = (
                self.queue_worker_thread.name if self.queue_worker_thread else None
            )
            stats["calling_thread"] = threading.current_thread().name
            return stats

    def wait_for_queue_empty(self, timeout: int = 30) -> bool:
        """Wait for the operation queue to become empty

        Args:
            timeout: Maximum time to wait in seconds

        Returns:
            True if queue became empty, False if timeout occurred
        """
        start_time = time.time()
        while time.time() - start_time < timeout:
            if self.operation_queue.empty():
                self.logger.debug("Queue is now empty")
                return True
            time.sleep(0.1)

        self.logger.warning(f"Timeout waiting for queue to empty after {timeout}s")
        return False

    def clear_queue(self) -> int:
        """Clear all pending operations from the queue

        Returns:
            Number of operations that were cleared
        """
        cleared_count = 0
        with self.queue_lock:
            while not self.operation_queue.empty():
                try:
                    operation = self.operation_queue.get_nowait()
                    if operation is not None:
                        operation.set_exception(
                            Exception("Operation cancelled - queue cleared")
                        )
                        cleared_count += 1
                        self.operation_queue.task_done()
                except queue.Empty:
                    break

        self.logger.info(f"🧹 Cleared {cleared_count} operations from queue")
        return cleared_count

    def is_thread_safe_call(self) -> bool:
        """Check if the current call is being made in a thread-safe manner

        Returns:
            True if the call is thread-safe (either from the queue worker or properly queued)
        """
        current_thread = threading.current_thread()

        # If we're the queue worker thread, we're safe
        if current_thread == self.queue_worker_thread:
            return True

        # If we're calling through the queue system, we're safe
        # This is harder to detect, so we assume external calls are properly queued
        return True  # The queue system handles this automatically

    def start(self) -> None:
        """Initialize the browser and start queue worker"""
        if self.driver is None:
            self.driver = self._create_webdriver()
            self._update_requests_session()

        # Start queue worker thread if not already running
        self._start_queue_worker()

    def close(self) -> None:
        """Close the browser and cleanup"""
        self.logger.info("💯 Starting cleanup process...")

        # Stop queue worker first
        self._stop_queue_worker()

        if self.driver:
            try:
                # Try graceful shutdown first
                self.logger.debug("🔄 Attempting graceful driver shutdown...")
                if os.name == "nt":
                    self.driver.close()
                self.driver.quit()
                self.logger.debug("✅ Driver shutdown completed")
            except Exception as e:
                self.logger.warning(f"⚠️ Error during graceful driver shutdown: {e}")
            finally:
                self.driver = None

        # Force kill any remaining Chrome processes
        self.logger.debug("🔫 Force killing any remaining Chrome processes...")
        self._kill_chrome_processes()

        self.logger.info("🧹 Cleanup completed successfully")

    def _create_webdriver(self) -> uc.Chrome:
        """Create undetected Chrome webdriver with optimal settings"""
        self.logger.info("Creating undetected Chrome webdriver...")

        options = uc.ChromeOptions()
        options.add_argument("--window-position=-10000,0")
        options.add_argument("--no-sandbox")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--disable-search-engine-choice-screen")
        options.add_argument("--disable-setuid-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--no-zygote")
        options.add_argument("--disable-blink-features=AutomationControlled")
        # Note: Some Chrome options may not be compatible with all versions

        # ARM architecture support
        if platform.machine().startswith(("arm", "aarch")):
            options.add_argument("--disable-gpu-sandbox")

        options.add_argument("--ignore-certificate-errors")
        options.add_argument("--ignore-ssl-errors")

        # Language setting
        language = os.environ.get("LANG", "en-US")
        options.add_argument(f"--accept-lang={language}")

        # Use headless only if hide_window is False
        use_headless = self.headless and not self.hide_window
        windows_headless = use_headless and os.name == "nt"

        try:
            # 1. Snapshot existing Chrome processes
            initial_pids = set()
            for proc in psutil.process_iter(["pid", "name"]):
                try:
                    if "chrome" in proc.info["name"].lower():
                        initial_pids.add(proc.pid)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

            driver = uc.Chrome(
                options=options,
                windows_headless=windows_headless,
                headless=use_headless and os.name != "nt",
            )

            # 2. Identify new Chrome processes
            final_pids = set()
            for proc in psutil.process_iter(["pid", "name"]):
                try:
                    if "chrome" in proc.info["name"].lower():
                        final_pids.add(proc.pid)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

            # 3. Store only the new PIDs
            new_pids = final_pids - initial_pids
            self.my_chrome_pids = new_pids
            self.logger.info(
                f"🎯 Identified {len(self.my_chrome_pids)} Chrome processes belonging to this scraper"
            )

            # Register them for cleanup
            for pid in self.my_chrome_pids:
                try:
                    self._register_chrome_process(psutil.Process(pid))
                except:
                    pass

            # Execute script to remove webdriver property
            driver.execute_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )

            # Get user agent
            self.user_agent = driver.execute_script("return navigator.userAgent")
            self.logger.info(f"Browser User-Agent: {self.user_agent}")

            # Hide Chrome windows if requested and not in headless mode
            if self.hide_window and not use_headless and platform.system() == "Windows":
                self.logger.info("Starting aggressive window hider...")
                def aggressive_hider():
                    # Try to hide windows immediately and repeatedly for the first few seconds
                    start_time = time.time()
                    while time.time() - start_time < 5:
                        self._hide_chrome_windows()
                        time.sleep(0.01)
                
                # Start hider in background immediately
                threading.Thread(target=aggressive_hider, daemon=True).start()

            return driver

        except Exception as e:
            self.logger.error(f"Error creating webdriver: {e}")
            raise

    def _update_requests_session(self) -> None:
        """Update requests session with current browser cookies and headers"""
        if not self.driver:
            return

        # Clear existing cookies
        self.session.cookies.clear()

        # Copy cookies from browser
        for cookie in self.driver.get_cookies():
            self.session.cookies.set(
                cookie["name"],
                cookie["value"],
                domain=cookie.get("domain"),
                path=cookie.get("path", "/"),
            )

        # Update headers
        self.session.headers.update(
            {
                "User-Agent": self.user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "DNT": "1",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
            }
        )

    def _detect_challenge(self) -> bool:
        """Detect if there's a Cloudflare challenge"""
        if not self.driver:
            return False

        page_title = self.driver.title

        # Check title-based detection
        for title in CHALLENGE_TITLES:
            if title.lower() == page_title.lower():
                self.logger.info(f"Challenge detected by title: {page_title}")
                return True

        # Check selector-based detection
        for selector in CHALLENGE_SELECTORS:
            found_elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
            if len(found_elements) > 0:
                self.logger.info(f"Challenge detected by selector: {selector}")
                return True

        return False

    def _wait_for_challenge_completion(self, timeout: int = None) -> bool:
        """Wait for Cloudflare challenge to complete"""
        timeout = timeout or self.timeout
        self.logger.info("Waiting for challenge to complete...")

        html_element = self.driver.find_element(By.TAG_NAME, "html")
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                # Wait until challenge titles disappear
                for title in CHALLENGE_TITLES:
                    WebDriverWait(self.driver, 1).until_not(title_is(title))

                # Wait until challenge selectors disappear
                for selector in CHALLENGE_SELECTORS:
                    WebDriverWait(self.driver, 1).until_not(
                        presence_of_element_located((By.CSS_SELECTOR, selector))
                    )

                break

            except TimeoutException:
                continue

        # Wait for redirect
        try:
            WebDriverWait(self.driver, 2).until(staleness_of(html_element))
        except TimeoutException:
            pass

        self.logger.info("Challenge resolution complete!")
        return True

    def goto(
        self, url: str, wait_for_load: bool = True, timeout: int = None
    ) -> Dict[str, Any]:
        """
        Navigate to a URL and handle challenges (THREAD-SAFE)

        Args:
            url: URL to navigate to
            wait_for_load: Wait for page to fully load
            timeout: Operation timeout

        Returns:
            Dict with page information
        """
        return self._submit_operation(
            "goto", url, wait_for_load=wait_for_load, timeout=timeout
        )

    def _internal_goto(self, url: str, wait_for_load: bool = True) -> Dict[str, Any]:
        """
        Internal implementation of goto - called by queue worker
        """
        if not self.driver:
            self.start()

        self.logger.info(f"Navigating to: {url}")
        self.driver.get(url)
        self.current_url = url

        # Handle challenges
        if self._detect_challenge():
            self.logger.info("Cloudflare challenge detected, waiting for resolution...")
            self._wait_for_challenge_completion()

        # Wait for page load if requested
        if wait_for_load:
            time.sleep(2)

        # Update requests session with new cookies
        self._update_requests_session()

        result = {
            "url": self.driver.current_url,
            "title": self.driver.title,
            "status": "success",
            "cookies": len(self.driver.get_cookies()),
        }

        self.logger.info(f"✓ Successfully accessed: {result['url']}")
        return result

    def get_html(self, url: str = None, timeout: int = None) -> str:
        """
        Get HTML content from current page or navigate to URL (THREAD-SAFE)

        Args:
            url: Optional URL to navigate to first
            timeout: Operation timeout

        Returns:
            HTML content as string
        """
        return self._submit_operation("get_html", url, timeout=timeout)

    def _internal_get_html(self, url: str = None) -> str:
        """
        Internal implementation of get_html - called by queue worker
        """
        if url:
            self._internal_goto(url)

        if not self.driver:
            raise Exception("No active browser session")

        return self.driver.page_source

    def get_soup(self, url: str = None, timeout: int = None) -> BeautifulSoup:
        """
        Get BeautifulSoup object for current page or navigate to URL (THREAD-SAFE)

        Args:
            url: Optional URL to navigate to first
            timeout: Operation timeout

        Returns:
            BeautifulSoup object
        """
        return self._submit_operation("get_soup", url, timeout=timeout)

    def _internal_get_soup(self, url: str = None) -> BeautifulSoup:
        """
        Internal implementation of get_soup - called by queue worker
        """
        html = self._internal_get_html(url)
        return BeautifulSoup(html, "html.parser")

    def find_element(self, selector: str, by: str = "css", timeout: int = None) -> Any:
        """
        Find a single element by CSS selector or XPath (THREAD-SAFE)

        Args:
            selector: CSS selector or XPath
            by: 'css' or 'xpath'
            timeout: Operation timeout

        Returns:
            WebElement or None
        """
        return self._submit_operation("find_element", selector, by=by, timeout=timeout)

    def _internal_find_element(self, selector: str, by: str = "css") -> Any:
        """
        Internal implementation of find_element - called by queue worker
        """
        if not self.driver:
            raise Exception("No active browser session")

        try:
            if by.lower() == "css":
                return self.driver.find_element(By.CSS_SELECTOR, selector)
            elif by.lower() == "xpath":
                return self.driver.find_element(By.XPATH, selector)
            else:
                raise ValueError("by must be 'css' or 'xpath'")
        except NoSuchElementException:
            return None

    def find_elements(
        self,
        selector: str, by: str = "css", timeout: int = None
    ) -> List[Any]:
        """
        Find multiple elements by CSS selector or XPath (THREAD-SAFE)

        Args:
            selector: CSS selector or XPath
            by: 'css' or 'xpath'
            timeout: Operation timeout

        Returns:
            List of WebElements
        """
        return self._submit_operation("find_elements", selector, by=by, timeout=timeout)

    def _internal_find_elements(self, selector: str, by: str = "css") -> List[Any]:
        """
        Internal implementation of find_elements - called by queue worker
        """
        if not self.driver:
            raise Exception("No active browser session")

        if by.lower() == "css":
            return self.driver.find_elements(By.CSS_SELECTOR, selector)
        elif by.lower() == "xpath":
            return self.driver.find_elements(By.XPATH, selector)
        else:
            raise ValueError("by must be 'css' or 'xpath'")

    def click(
        self,
        selector: str, by: str = "css", wait: bool = True, timeout: int = None
    ) -> bool:
        """
        Click on an element (THREAD-SAFE)

        Args:
            selector: CSS selector or XPath
            by: 'css' or 'xpath'
            wait: Wait for element to be clickable
            timeout: Operation timeout

        Returns:
            True if clicked successfully
        """
        return self._submit_operation(
            "click", selector, by=by, wait=wait, timeout=timeout
        )

    def _internal_click(
        self,
        selector: str, by: str = "css", wait: bool = True
    ) -> bool:
        """
        Internal implementation of click - called by queue worker
        """
        try:
            if wait:
                if by.lower() == "css":
                    element = WebDriverWait(self.driver, self.timeout).until(
                        element_to_be_clickable((By.CSS_SELECTOR, selector))
                    )
                else:
                    element = WebDriverWait(self.driver, self.timeout).until(
                        element_to_be_clickable((By.XPATH, selector))
                    )
            else:
                element = self._internal_find_element(selector, by)

            if element:
                # Scroll to element
                self.driver.execute_script(
                    "arguments[0].scrollIntoView(true);", element
                )
                time.sleep(0.5)

                # Try regular click first
                try:
                    element.click()
                except Exception:
                    # If regular click fails, try JavaScript click
                    self.driver.execute_script("arguments[0].click();", element)

                self.logger.info(f"✓ Clicked element: {selector}")
                return True
            else:
                self.logger.warning(f"Element not found: {selector}")
                return False

        except Exception as e:
            self.logger.error(f"Error clicking element {selector}: {e}")
            return False

    def type_text(
        self,
        selector: str, text: str, by: str = "css", clear: bool = True
    ) -> bool:
        """
        Type text into an input field

        Args:
            selector: CSS selector or XPath
            text: Text to type
            by: 'css' or 'xpath'
            clear: Clear field before typing

        Returns:
            True if successful
        """
        try:
            element = self.find_element(selector, by)
            if element:
                if clear:
                    element.clear()
                element.send_keys(text)
                self.logger.info(f"✓ Typed text into: {selector}")
                return True
            else:
                self.logger.warning(f"Element not found: {selector}")
                return False
        except Exception as e:
            self.logger.error(f"Error typing text into {selector}: {e}")
            return False

    def wait_for_element(
        self,
        selector: str, by: str = "css", timeout: int = None
    ) -> Any:
        """
        Wait for an element to appear

        Args:
            selector: CSS selector or XPath
            by: 'css' or 'xpath'
            timeout: Timeout in seconds

        Returns:
            WebElement or None
        """
        timeout = timeout or self.timeout
        try:
            if by.lower() == "css":
                element = WebDriverWait(self.driver, timeout).until(
                    presence_of_element_located((By.CSS_SELECTOR, selector))
                )
            else:
                element = WebDriverWait(self.driver, timeout).until(
                    presence_of_element_located((By.XPATH, selector))
                )
            return element
        except TimeoutException:
            return None

    def wait_for_element_attribute(
        self,
        selector: str,
        attribute: str,
        expected_value: str = None,
        by: str = "css",
        timeout: int = None,
        wait_for_change: bool = False,
    ) -> bool:
        """
        Wait for an element's attribute to have a specific value or to change

        Args:
            selector: CSS selector or XPath
            attribute: Attribute name (e.g., 'hidden', 'class', 'style')
            expected_value: Expected attribute value (None means attribute should exist)
            by: 'css' or 'xpath'
            timeout: Timeout in seconds
            wait_for_change: If True, wait for attribute to change from current value

        Returns:
            True if condition met, False if timeout

        Examples:
            # Wait for element to become hidden
            scraper.wait_for_element_attribute('.loading', 'hidden')

            # Wait for element to have specific class
            scraper.wait_for_element_attribute('#status', 'class', 'completed')

            # Wait for style attribute to change
            scraper.wait_for_element_attribute('.modal', 'style', wait_for_change=True)
        """
        timeout = timeout or self.timeout
        self.logger.debug(
            f"Waiting for element '{selector}' attribute '{attribute}' = '{expected_value}'"
        )

        try:
            element = self.find_element(selector, by)
            if not element:
                self.logger.warning(f"Element '{selector}' not found")
                return False

            # Get initial value if waiting for change
            initial_value = None
            if wait_for_change:
                initial_value = element.get_attribute(attribute)
                self.logger.debug(f"Initial attribute value: '{initial_value}'")

            def check_attribute():
                current_element = self.find_element(selector, by)
                if not current_element:
                    return False

                current_value = current_element.get_attribute(attribute)

                if wait_for_change:
                    return current_value != initial_value
                elif expected_value is None:
                    # Just check if attribute exists (not None)
                    return current_value is not None
                else:
                    # Check for specific value
                    if attribute == "class":
                        # For class attribute, check if expected_value is in the class list
                        return expected_value in (current_value or "").split()
                    else:
                        return current_value == expected_value

            # Wait for condition
            start_time = time.time()
            while time.time() - start_time < timeout:
                if check_attribute():
                    self.logger.debug(f"Attribute condition met for '{selector}'")
                    return True
                time.sleep(0.5)

            self.logger.warning(
                f"Timeout waiting for attribute condition on '{selector}'"
            )
            return False

        except Exception as e:
            self.logger.error(f"Error waiting for element attribute: {e}")
            return False

    def wait_for_captcha(
        self,
        timeout: int = 60, auto_solve: bool = True
    ) -> Dict[str, Any]:
        """
        Wait for and optionally attempt to solve CAPTCHAs

        Args:
            timeout: Maximum time to wait for CAPTCHA completion
            auto_solve: Attempt to automatically solve simple CAPTCHAs

        Returns:
            Dict with CAPTCHA status and type information

        Examples:
            # Wait for any CAPTCHA to be solved (manually or automatically)
            result = scraper.wait_for_captcha(timeout=60)

            # Just detect CAPTCHA without trying to solve
            result = scraper.wait_for_captcha(auto_solve=False)
        """
        self.logger.info("Checking for CAPTCHAs...")

        result = {
            "captcha_detected": False,
            "captcha_type": None,
            "solved": False,
            "time_taken": 0,
        }

        start_time = time.time()

        try:
            # Check for different types of CAPTCHAs
            captcha_info = self._detect_captcha_type()

            if not captcha_info["detected"]:
                self.logger.debug("No CAPTCHA detected")
                return result

            result["captcha_detected"] = True
            result["captcha_type"] = captcha_info["type"]

            self.logger.info(f"CAPTCHA detected: {captcha_info['type']}")

            if auto_solve:
                self.logger.info("Attempting to solve CAPTCHA...")
                solved = self._attempt_captcha_solve(captcha_info, timeout)
                result["solved"] = solved

                if solved:
                    self.logger.info("CAPTCHA solved successfully!")
                else:
                    self.logger.warning("CAPTCHA could not be solved automatically")
            else:
                # Wait for manual solving
                self.logger.info("Waiting for manual CAPTCHA solving...")
                solved = self._wait_for_captcha_completion(captcha_info, timeout)
                result["solved"] = solved

            result["time_taken"] = time.time() - start_time
            return result

        except Exception as e:
            self.logger.error(f"Error handling CAPTCHA: {e}")
            result["time_taken"] = time.time() - start_time
            return result

    def _detect_captcha_type(self) -> Dict[str, Any]:
        """
        Detect what type of CAPTCHA is present on the page
        """
        if not self.driver:
            return {"detected": False, "type": None, "elements": []}

        captcha_types = {
            "recaptcha_v2": {
                "selectors": [
                    ".g-recaptcha",
                    'iframe[src*="recaptcha"]',
                    ".recaptcha-checkbox",
                ],
                "iframe_src": "recaptcha",
            },
            "hcaptcha": {
                "selectors": [".hcaptcha-checkbox", 'iframe[src*="hcaptcha"]'],
                "iframe_src": "hcaptcha",
            },
            "turnstile": {
                "selectors": [".cf-turnstile", "[data-cf-turnstile-sitekey]"],
                "iframe_src": "turnstile",
            },
            "generic": {
                "selectors": ["[data-sitekey]", ".captcha", "#captcha"],
                "iframe_src": "captcha",
            },
        }

        for captcha_type, config in captcha_types.items():
            elements = []
            for selector in config["selectors"]:
                found = self.find_elements(selector)
                if found:
                    elements.extend(found)

            if elements:
                self.logger.debug(f"Detected {captcha_type} CAPTCHA")
                return {
                    "detected": True,
                    "type": captcha_type,
                    "elements": elements,
                    "config": config,
                }

        return {"detected": False, "type": None, "elements": []}

    def _attempt_captcha_solve(self, captcha_info: Dict, timeout: int) -> bool:
        """
        Attempt to automatically solve CAPTCHA
        """
        captcha_type = captcha_info["type"]

        try:
            if captcha_type == "recaptcha_v2":
                return self._solve_recaptcha_v2(captcha_info, timeout)
            elif captcha_type == "hcaptcha":
                return self._solve_hcaptcha(captcha_info, timeout)
            elif captcha_type == "turnstile":
                return self._solve_turnstile(captcha_info, timeout)
            else:
                self.logger.warning(f"No automatic solver for {captcha_type}")
                return self._wait_for_captcha_completion(captcha_info, timeout)

        except Exception as e:
            self.logger.error(f"Error solving {captcha_type}: {e}")
            return False

    def _solve_recaptcha_v2(self, captcha_info: Dict, timeout: int) -> bool:
        """
        Attempt to solve reCAPTCHA v2 (mainly clicking the checkbox)
        """
        self.logger.debug("Attempting to solve reCAPTCHA v2...")

        try:
            # Look for the checkbox iframe
            checkbox_iframe = self.find_element(
                'iframe[src*="recaptcha"][src*="anchor"]'
            )
            if checkbox_iframe:
                self.logger.debug("Found reCAPTCHA checkbox iframe")

                # Switch to iframe and click checkbox
                self.driver.switch_to.frame(checkbox_iframe)

                checkbox = self.find_element(".recaptcha-checkbox-border")
                if checkbox and checkbox.is_enabled():
                    self.logger.debug("Clicking reCAPTCHA checkbox")
                    checkbox.click()
                    time.sleep(2)

                # Switch back to main content
                self.driver.switch_to.default_content()

                # Wait for completion or challenge
                return self._wait_for_captcha_completion(captcha_info, timeout)

        except Exception as e:
            self.logger.error(f"Error solving reCAPTCHA v2: {e}")
            try:
                self.driver.switch_to.default_content()
            except:
                pass

        return False

    def _solve_hcaptcha(self, captcha_info: Dict, timeout: int) -> bool:
        """
        Attempt to solve hCaptcha (mainly clicking the checkbox)
        """
        self.logger.debug("Attempting to solve hCaptcha...")

        try:
            # Look for hCaptcha checkbox
            checkbox = self.find_element(".hcaptcha-checkbox")
            if checkbox and checkbox.is_enabled():
                self.logger.debug("Clicking hCaptcha checkbox")
                checkbox.click()
                time.sleep(2)

                return self._wait_for_captcha_completion(captcha_info, timeout)

        except Exception as e:
            self.logger.error(f"Error solving hCaptcha: {e}")

        return False

    def _solve_turnstile(self, captcha_info: Dict, timeout: int) -> bool:
        """
        Attempt to solve Cloudflare Turnstile (usually automatic)
        """
        self.logger.debug("Waiting for Turnstile to complete...")

        # Turnstile usually solves automatically, just wait
        return self._wait_for_captcha_completion(captcha_info, timeout)

    def _wait_for_captcha_completion(self, captcha_info: Dict, timeout: int) -> bool:
        """
        Wait for CAPTCHA to be completed (either automatically or manually)
        """
        start_time = time.time()

        while time.time() - start_time < timeout:
            # Check if CAPTCHA elements are still visible/active
            current_captcha = self._detect_captcha_type()

            if not current_captcha["detected"]:
                self.logger.debug("CAPTCHA no longer detected - assuming solved")
                return True

            # For reCAPTCHA, check for success indicators
            if captcha_info["type"] == "recaptcha_v2":
                success_elements = self.find_elements(".recaptcha-checkbox-checked")
                if success_elements:
                    self.logger.debug("reCAPTCHA checkbox checked")
                    return True

            # Check if page has changed significantly (might indicate success)
            try:
                current_url = self.driver.current_url
                if (
                    hasattr(self, "captcha_start_url")
                    and current_url != self.captcha_start_url
                ):
                    self.logger.debug("Page URL changed - CAPTCHA likely solved")
                    return True
            except:
                pass

            time.sleep(1)

        self.logger.warning(
            f"Timeout waiting for CAPTCHA completion after {timeout} seconds"
        )
        return False

    def download_file(
        self,
        url: str,
        filename: str = None,
        use_browser: bool = True,
        timeout: int = None,
    ) -> Optional[str]:
        """
        Download a file using either browser session or requests (THREAD-SAFE)

        Args:
            url: URL of file to download
            filename: Optional filename (auto-detected if None)
            use_browser: Use browser session (recommended for protected files)
            timeout: Operation timeout

        Returns:
            Path to downloaded file or None if failed
        """
        return self._submit_operation(
            "download_file",
            url, filename=filename, use_browser=use_browser, timeout=timeout
        )

    def _internal_download_file(
        self, url: str, filename: str = None, use_browser: bool = True, gave_path=False
    ) -> Optional[str]:
        """
        Internal implementation of download_file - called by queue worker
        """
        try:
            # Resolve relative URLs
            if self.current_url and not url.startswith(("http://", "https://")):
                url = urljoin(self.current_url, url)

            self.logger.info(f"Downloading file: {url}")

            if use_browser and self.driver:
                # Update session first
                self._update_requests_session()

                # Set appropriate headers for file download
                headers = {
                    "Accept": "*/*",
                    "Referer": self.current_url or self.driver.current_url,
                }

                # Detect file type and set appropriate accept header
                if any(
                    ext in url.lower()
                    for ext in [".jpg", ".jpeg", ".png", ".gif", ".webp"]
                ):
                    headers["Accept"] = (
                        "image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8"
                    )
                elif any(ext in url.lower() for ext in [".css"]):
                    headers["Accept"] = "text/css,*/*;q=0.1"
                elif any(ext in url.lower() for ext in [".js"]):
                    headers["Accept"] = "*/*"

                response = self.session.get(url, stream=True, headers=headers)
            else:
                # Use basic requests without browser session
                response = requests.get(url, stream=True)

            response.raise_for_status()

            # Determine filename
            if not filename:
                # Try to get filename from Content-Disposition header
                cd_header = response.headers.get("content-disposition", "")
                if "filename=" in cd_header:
                    filename = cd_header.split("filename=")[1].strip("\"'")
                else:
                    # Extract from URL
                    filename = os.path.basename(urlparse(url).path)
                    if not filename or "." not in filename:
                        # Generate filename based on content type
                        content_type = response.headers.get("content-type", "")
                        if "image" in content_type:
                            ext = content_type.split("/")[-1]
                            filename = f"image_{int(time.time())}.{ext}"
                        else:
                            filename = f"file_{int(time.time())}"

            # Ensure filename is safe
            filename = re.sub(r'[<>:"/\\|?*]', "_", filename)
            if gave_path:
                filename = filename.split("_")[-1]
            filepath = self.download_dir / filename

            # Download file
            with open(filepath, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

            file_size = filepath.stat().st_size
            self.logger.info(f"✓ File downloaded successfully!")
            self.logger.info(f"  Path: {filepath}")
            self.logger.info(
                f"  Size: {file_size / 1024:.1f} KB"
            )
            self.logger.info(
                f"  Content-Type: {response.headers.get('content-type', 'Unknown')}"
            )

            return str(filepath)

        except Exception as e:
            self.logger.error(f"Error downloading file {url}: {e}")
            return None

    def download_all_images(
        self,
        selector: str = "img", attribute: str = "src"
    ) -> List[str]:
        """
        Download all images from the current page

        Args:
            selector: CSS selector for image elements
            attribute: Attribute containing image URL

        Returns:
            List of downloaded file paths
        """
        if not self.driver:
            raise Exception("No active browser session")

        images = self.find_elements(selector)
        downloaded = []

        for img in images:
            try:
                img_url = img.get_attribute(attribute)
                if img_url:
                    filepath = self.download_file(img_url)
                    if filepath:
                        downloaded.append(filepath)
            except Exception as e:
                self.logger.warning(f"Failed to download image: {e}")
                continue

        self.logger.info(f"Downloaded {len(downloaded)} images")
        return downloaded

    def screenshot(self, filename: str = None) -> str:
        """
        Take a screenshot of the current page

        Args:
            filename: Optional filename

        Returns:
            Path to screenshot file
        """
        if not self.driver:
            raise Exception("No active browser session")

        if not filename:
            filename = f"screenshot_{int(time.time())}.png"

        filepath = self.download_dir / filename
        self.driver.save_screenshot(str(filepath))

        self.logger.info(f"Screenshot saved: {filepath}")
        return str(filepath)

    def scroll_to_bottom(self, pause_time: float = 1.0) -> None:
        """
        Scroll to bottom of page with pauses to load content

        Args:
            pause_time: Time to pause between scrolls
        """
        if not self.driver:
            raise Exception("No active browser session")

        last_height = self.driver.execute_script("return document.body.scrollHeight")

        while True:
            # Scroll down to bottom
            self.driver.execute_script(
                "window.scrollTo(0, document.body.scrollHeight);"
            )

            # Wait for new content to load
            time.sleep(pause_time)

            # Calculate new scroll height
            new_height = self.driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height

        self.logger.info("Scrolled to bottom of page")

    def execute_script(self, script: str, *args) -> Any:
        """
        Execute JavaScript in the browser

        Args:
            script: JavaScript code to execute
            *args: Arguments to pass to the script

        Returns:
            Result of script execution
        """
        if not self.driver:
            raise Exception("No active browser session")

        return self.driver.execute_script(script, *args)

    def get_cookies(self) -> List[Dict]:
        """Get all cookies from the browser"""
        if not self.driver:
            return []
        return self.driver.get_cookies()

    def add_cookie(self, cookie_dict: Dict) -> None:
        """Add a cookie to the browser"""
        if self.driver:
            self.driver.add_cookie(cookie_dict)
            self._update_requests_session()
