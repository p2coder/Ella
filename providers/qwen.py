import base64
import json
import socket
from dataclasses import dataclass, field
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .base import ProviderError, ProviderResult


QwenClient = Callable[[dict[str, Any]], Any]
HttpOpener = Callable[[Request, float], Any]
DEFAULT_DASHSCOPE_ENDPOINT = (
    "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
)


class QwenTransportError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int | None = None,
    ) -> None:
        self.code = code
        self.status_code = status_code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class DashScopeOpenAITransport:
    endpoint: str = DEFAULT_DASHSCOPE_ENDPOINT
    timeout_seconds: float = 30.0
    opener: HttpOpener = urlopen

    def __call__(self, payload: dict[str, Any]) -> dict[str, Any]:
        api_key = payload["api_key"]
        if not api_key.startswith("sk-"):
            raise QwenTransportError(
                "provider_unavailable",
                "Qwen client is not configured",
            )

        request_body = self._request_body(payload)
        request = Request(
            self.endpoint,
            data=json.dumps(request_body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with self.opener(request, self.timeout_seconds) as response:
                body = response.read()
        except HTTPError as error:
            raise self._http_error(error.code) from None
        except (TimeoutError, socket.timeout):
            raise QwenTransportError(
                "timeout_error",
                "Qwen request timed out",
            ) from None
        except URLError as error:
            if isinstance(error.reason, (TimeoutError, socket.timeout)):
                raise QwenTransportError(
                    "timeout_error",
                    "Qwen request timed out",
                ) from None
            raise QwenTransportError(
                "transport_error",
                "Qwen request could not reach DashScope",
            ) from None
        except OSError:
            raise QwenTransportError(
                "transport_error",
                "Qwen request transport failed",
            ) from None

        try:
            response_payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise QwenTransportError(
                "malformed_response",
                "Qwen returned a malformed JSON response",
            ) from None
        if not isinstance(response_payload, dict):
            raise QwenTransportError(
                "malformed_response",
                "Qwen returned an unexpected response shape",
            )
        return response_payload

    def _request_body(self, payload: dict[str, Any]) -> dict[str, Any]:
        input_payload = payload["input"]
        if "prompt" in input_payload:
            content: Any = input_payload["prompt"]
        else:
            content = self._multimodal_content(input_payload)
        return {
            "model": payload["model_name"],
            "messages": [{"role": "user", "content": content}],
        }

    def _multimodal_content(
        self,
        input_payload: dict[str, Any],
    ) -> list[dict[str, Any]]:
        prompt = (
            "Describe the scene for the task. Return JSON with scene_summary, "
            "visible_items, and umbrella_visible."
        )
        if input_payload.get("handoff_goal"):
            prompt += f" Task goal: {input_payload['handoff_goal']}"

        content: list[dict[str, Any]] = [
            {"type": "text", "text": prompt}
        ]
        frames = input_payload.get("frames") or ()
        for frame in frames:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": self._image_url(frame)},
                }
            )
        if len(content) == 1:
            raise QwenTransportError(
                "missing_input",
                "Qwen multimodal input has no frames",
            )
        return content

    @staticmethod
    def _image_url(frame: Any) -> str:
        if isinstance(frame, bytes):
            image_bytes = frame
            mime_type = "image/jpeg"
        elif isinstance(frame, dict):
            image_bytes = frame.get("bytes", frame.get("data", frame.get("frame")))
            mime_type = frame.get("mime_type", "image/jpeg")
        else:
            image_bytes = None
            mime_type = "image/jpeg"

        if isinstance(image_bytes, str) and image_bytes.startswith(
            ("data:", "http://", "https://")
        ):
            return image_bytes
        if not isinstance(image_bytes, bytes):
            raise QwenTransportError(
                "invalid_input",
                "Qwen multimodal frame must contain encoded image bytes",
            )
        encoded = base64.b64encode(image_bytes).decode("ascii")
        return f"data:{mime_type};base64,{encoded}"

    @staticmethod
    def _http_error(status_code: int) -> QwenTransportError:
        if status_code in (401, 403):
            return QwenTransportError(
                "authentication_error",
                "DashScope rejected Qwen authentication",
                status_code=status_code,
            )
        if status_code == 429:
            return QwenTransportError(
                "rate_limit_error",
                "DashScope rate limit was exceeded",
                status_code=status_code,
            )
        return QwenTransportError(
            "provider_error",
            "DashScope returned a Qwen service error",
            status_code=status_code,
        )


@dataclass(frozen=True, slots=True)
class _QwenProviderBase:
    api_key: str | None = field(repr=False)
    model_name: str
    client: QwenClient | None = None

    @property
    def provider_name(self) -> str:
        raise NotImplementedError

    def _call(
        self,
        input_payload: dict[str, Any],
        *,
        trace_id: str | None,
        metadata: dict[str, Any] | None,
    ) -> ProviderResult:
        result_metadata = {
            **dict(metadata or {}),
            "real_provider_requested": True,
        }
        if self.api_key is None:
            return self._error_result(
                trace_id=trace_id,
                message="Qwen API key is missing",
                code="provider_unavailable",
                metadata={"missing": "ELLA_QWEN_API_KEY"},
            )
        if self.client is None:
            return self._error_result(
                trace_id=trace_id,
                message="Qwen client is not configured",
                code="provider_unavailable",
                metadata={"reason": "client_missing"},
            )

        try:
            raw_output = self.client(
                {
                    "api_key": self.api_key,
                    "model_name": self.model_name,
                    "input": input_payload,
                    "metadata": dict(metadata or {}),
                }
            )
            output = self._normalize_output(raw_output)
        except QwenTransportError as error:
            error_metadata: dict[str, Any] = {}
            if error.status_code is not None:
                error_metadata["status_code"] = error.status_code
            return self._error_result(
                trace_id=trace_id,
                message=str(error),
                code=error.code,
                metadata=error_metadata,
            )
        except Exception:
            return self._error_result(
                trace_id=trace_id,
                message="Qwen client transport failed",
                code="transport_error",
                metadata={},
            )

        return ProviderResult(
            provider_name=self.provider_name,
            model_name=self.model_name,
            trace_id=trace_id,
            output=output,
            metadata=result_metadata,
        )

    def _normalize_output(self, output: Any) -> dict[str, Any]:
        if isinstance(output, dict) and self._is_normalized(output):
            return output
        content = self._message_content(output)
        return self._normalize_content(content)

    def _is_normalized(self, output: dict[str, Any]) -> bool:
        raise NotImplementedError

    def _normalize_content(self, content: str) -> dict[str, Any]:
        raise NotImplementedError

    @staticmethod
    def _message_content(output: Any) -> str:
        try:
            content = output["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise QwenTransportError(
                "malformed_response",
                "Qwen response did not contain message content",
            ) from None
        if isinstance(content, list):
            content = "".join(
                str(item.get("text", ""))
                for item in content
                if isinstance(item, dict)
            )
        if not isinstance(content, str) or not content.strip():
            raise QwenTransportError(
                "malformed_response",
                "Qwen response message content was empty",
            )
        return content.strip()

    def _error_result(
        self,
        *,
        trace_id: str | None,
        message: str,
        code: str,
        metadata: dict[str, Any],
    ) -> ProviderResult:
        return ProviderResult(
            provider_name=self.provider_name,
            model_name=self.model_name,
            trace_id=trace_id,
            output=None,
            metadata={"real_provider_requested": True},
            error=ProviderError(
                provider_name=self.provider_name,
                message=message,
                code=code,
                metadata=metadata,
            ),
        )


@dataclass(frozen=True, slots=True)
class QwenLLMProvider(_QwenProviderBase):
    provider_name: str = "qwen_llm"

    def generate(
        self,
        prompt: str,
        *,
        trace_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ProviderResult:
        return self._call(
            {"prompt": prompt},
            trace_id=trace_id,
            metadata=metadata,
        )

    def _is_normalized(self, output: dict[str, Any]) -> bool:
        return isinstance(output.get("text"), str)

    def _normalize_content(self, content: str) -> dict[str, Any]:
        return {"text": content}


@dataclass(frozen=True, slots=True)
class QwenSpeechProvider(_QwenProviderBase):
    provider_name: str = "qwen_speech"

    def transcribe(
        self,
        audio: Any,
        *,
        trace_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ProviderResult:
        return self._call(
            {"audio": audio},
            trace_id=trace_id,
            metadata=metadata,
        )

    def _is_normalized(self, output: dict[str, Any]) -> bool:
        return isinstance(output.get("text"), str)

    def _normalize_content(self, content: str) -> dict[str, Any]:
        return {"text": content}


@dataclass(frozen=True, slots=True)
class QwenMultimodalProvider(_QwenProviderBase):
    provider_name: str = "qwen_multimodal"

    def describe(
        self,
        inputs: dict[str, Any],
        *,
        trace_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ProviderResult:
        return self._call(
            inputs,
            trace_id=trace_id,
            metadata=metadata,
        )

    def _is_normalized(self, output: dict[str, Any]) -> bool:
        return isinstance(output.get("scene_summary"), str)

    def _normalize_content(self, content: str) -> dict[str, Any]:
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            parsed = {"scene_summary": content}
        if not isinstance(parsed, dict) or not isinstance(
            parsed.get("scene_summary"), str
        ):
            raise QwenTransportError(
                "malformed_response",
                "Qwen multimodal response lacked scene_summary",
            )
        result = {"scene_summary": parsed["scene_summary"]}
        if "visible_items" in parsed:
            result["visible_items"] = tuple(parsed["visible_items"])
        if "umbrella_visible" in parsed:
            result["umbrella_visible"] = bool(parsed["umbrella_visible"])
        return result


QwenVisionProvider = QwenMultimodalProvider
