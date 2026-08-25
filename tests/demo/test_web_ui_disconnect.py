from demo.web_ui import _QuietClientDisconnectMixin


class RecordingServer:
    def __init__(self) -> None:
        self.reported = []

    def handle_error(self, request, client_address) -> None:
        self.reported.append(client_address)


class QuietRecordingServer(_QuietClientDisconnectMixin, RecordingServer):
    pass


def test_client_connection_reset_is_not_reported() -> None:
    server = QuietRecordingServer()

    try:
        raise ConnectionResetError(54, "Connection reset by peer")
    except ConnectionResetError:
        server.handle_error(None, ("127.0.0.1", 50022))

    assert server.reported == []


def test_unexpected_server_error_uses_standard_reporting() -> None:
    server = QuietRecordingServer()

    try:
        raise ValueError("request handler failed")
    except ValueError:
        server.handle_error(None, ("127.0.0.1", 50023))

    assert server.reported == [("127.0.0.1", 50023)]
