import errno
import webbrowser
from collections.abc import Callable
from http.server import ThreadingHTTPServer

from app_runtime import AppRuntime
from demo.web_ui import DEFAULT_HOST, DEFAULT_PORT, create_server


MAX_PORT_ATTEMPTS = 100


def create_server_on_available_port(
    app_runtime: AppRuntime,
    *,
    host: str = DEFAULT_HOST,
    start_port: int = DEFAULT_PORT,
    max_attempts: int = MAX_PORT_ATTEMPTS,
    server_factory: Callable[..., ThreadingHTTPServer] = create_server,
) -> ThreadingHTTPServer:
    for port in range(start_port, start_port + max_attempts):
        try:
            return server_factory(app_runtime, host=host, port=port)
        except OSError as error:
            if error.errno != errno.EADDRINUSE:
                raise
    raise RuntimeError(
        f"no available local port in range {start_port}-"
        f"{start_port + max_attempts - 1}"
    )


def run_web_app(
    app_runtime: AppRuntime,
    *,
    server_factory: Callable[..., ThreadingHTTPServer] = (
        create_server_on_available_port
    ),
    browser_opener: Callable[[str], object] = webbrowser.open,
) -> None:
    server = server_factory(app_runtime)
    host, port = server.server_address[:2]
    url = f"http://{host}:{port}"
    print(f"Ella Runtime is available at {url}")
    browser_opener(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Ella Runtime.")
    finally:
        server.server_close()


def main() -> int:
    run_web_app(AppRuntime.create_default())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
