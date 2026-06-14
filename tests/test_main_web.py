import errno

import main as main_module


class RecordingServer:
    def __init__(self, port: int) -> None:
        self.server_address = ("127.0.0.1", port)
        self.served = False

    def serve_forever(self) -> None:
        self.served = True

    def server_close(self) -> None:
        return


def test_create_server_uses_next_available_port():
    attempts: list[int] = []

    def server_factory(_runtime, *, host: str, port: int):
        assert host == "127.0.0.1"
        attempts.append(port)
        if port < 8002:
            raise OSError(errno.EADDRINUSE, "address already in use")
        return RecordingServer(port)

    server = main_module.create_server_on_available_port(
        object(),
        server_factory=server_factory,
    )

    assert attempts == [8000, 8001, 8002]
    assert server.server_address == ("127.0.0.1", 8002)


def test_run_web_app_opens_browser_and_serves():
    server = RecordingServer(8010)
    opened: list[str] = []

    main_module.run_web_app(
        object(),
        server_factory=lambda *_args, **_kwargs: server,
        browser_opener=opened.append,
    )

    assert opened == ["http://127.0.0.1:8010"]
    assert server.served is True


def test_main_builds_formal_app_runtime(monkeypatch):
    created: list[object] = []
    served: list[object] = []

    class RecordingAppRuntime:
        @classmethod
        def create_default(cls):
            instance = cls()
            created.append(instance)
            return instance

    monkeypatch.setattr(main_module, "AppRuntime", RecordingAppRuntime)
    monkeypatch.setattr(
        main_module,
        "run_web_app",
        lambda runtime: served.append(runtime),
    )

    assert main_module.main() == 0
    assert served == created
