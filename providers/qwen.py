import base64
import json
import socket
from dataclasses import dataclass, field
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .base import ProviderError, ProviderResult
from .llm import serialize_tool_definition


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
            with self.opener(request, timeout=self.timeout_seconds) as response:
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
        elif "audio" in input_payload:
            return self._speech_request_body(
                model_name=payload["model_name"],
                audio=input_payload["audio"],
            )
        else:
            content = self._multimodal_content(input_payload)
        body: dict[str, Any] = {
            "model": payload["model_name"],
            "messages": [{"role": "user", "content": content}],
        }
        if "tools" in input_payload:
            body["tools"] = input_payload["tools"]
            body["tool_choice"] = "auto"
        return body

    def _speech_request_body(
        self,
        *,
        model_name: str,
        audio: Any,
    ) -> dict[str, Any]:
        return {
            "model": model_name,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_audio",
                            "input_audio": {"data": self._audio_data_url(audio)},
                        }
                    ],
                }
            ],
            "stream": False,
            "asr_options": {"enable_itn": False},
        }

    @staticmethod
    def _audio_data_url(audio: Any) -> str:
        if not isinstance(audio, dict):
            raise QwenTransportError(
                "invalid_audio_format",
                "Qwen speech input must contain bounded audio metadata",
            )

        audio_bytes = audio.get("bytes")
        mime_type = audio.get("mime_type")
        sample_rate = audio.get("sample_rate")
        channels = audio.get("channels")
        supported_mime_types = {
            "audio/L16": "audio/pcm",
            "audio/pcm": "audio/pcm",
            "audio/wav": "audio/wav",
            "audio/x-wav": "audio/wav",
            "audio/mpeg": "audio/mpeg",
            "audio/mp4": "audio/mp4",
            "audio/ogg": "audio/ogg",
            "audio/flac": "audio/flac",
            "audio/x-flac": "audio/flac",
        }
        is_valid_pcm_rate = mime_type != "audio/L16" or sample_rate == 16_000
        if (
            not isinstance(audio_bytes, bytes)
            or not audio_bytes
            or mime_type not in supported_mime_types
            or not isinstance(sample_rate, int)
            or sample_rate <= 0
            or not isinstance(channels, int)
            or channels <= 0
            or not is_valid_pcm_rate
        ):
            raise QwenTransportError(
                "invalid_audio_format",
                "Qwen speech input has unsupported audio data or metadata",
            )

        encoded = base64.b64encode(audio_bytes).decode("ascii")
        normalized_mime = supported_mime_types[mime_type]
        return f"data:{normalized_mime};base64,{encoded}"

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


def qwen_tools_from_definitions(
    definitions: tuple[Any, ...],
) -> tuple[dict[str, Any], ...]:
    return tuple(_qwen_tool_from_definition(definition) for definition in definitions)


def qwen_tool_call_to_decision(
    response: Any,
    *,
    known_tool_names: tuple[str, ...],
) -> dict[str, Any]:
    tool_call = _first_tool_call(response)
    if tool_call is None:
        return _tool_decision_error(
            code="missing_tool_call",
            message="Qwen response did not include a tool call.",
        )

    function = tool_call.get("function")
    if not isinstance(function, dict):
        return _tool_decision_error(
            code="malformed_tool_call",
            message="Qwen tool call did not include a function object.",
        )

    tool_name = function.get("name")
    arguments_text = function.get("arguments")
    if not isinstance(tool_name, str) or not tool_name:
        return _tool_decision_error(
            code="malformed_tool_call",
            message="Qwen tool call did not include a function name.",
        )
    if tool_name not in known_tool_names:
        return _tool_decision_error(
            code="unknown_tool",
            message=f"Qwen requested unknown tool: {tool_name}",
        )
    if not isinstance(arguments_text, str):
        return _tool_decision_error(
            code="malformed_tool_call",
            message="Qwen tool call did not include JSON arguments.",
        )

    try:
        arguments = json.loads(arguments_text)
    except json.JSONDecodeError:
        return _tool_decision_error(
            code="malformed_tool_call",
            message="Qwen tool call arguments were not valid JSON.",
        )
    if not isinstance(arguments, dict):
        return _tool_decision_error(
            code="malformed_tool_call",
            message="Qwen tool call arguments must decode to an object.",
        )

    return {
        "action": "CALL_TOOL",
        "tool_name": tool_name,
        "arguments": arguments,
        "reason": f"Qwen requested tool {tool_name}.",
    }


def _qwen_tool_from_definition(definition: Any) -> dict[str, Any]:
    if isinstance(definition, dict):
        serialized = definition
    else:
        serialized = serialize_tool_definition(definition)
    return {
        "type": "function",
        "function": {
            "name": serialized["name"],
            "description": serialized["description"],
            "parameters": serialized["input_schema"],
        },
    }


def _first_tool_call(response: Any) -> dict[str, Any] | None:
    try:
        tool_calls = response["choices"][0]["message"]["tool_calls"]
    except (KeyError, IndexError, TypeError):
        return None
    if not isinstance(tool_calls, list) or not tool_calls:
        return None
    first = tool_calls[0]
    if not isinstance(first, dict):
        return None
    return first


def _tool_decision_error(*, code: str, message: str) -> dict[str, Any]:
    return {
        "action": "REPLAN",
        "reason": message,
        "error": {
            "code": code,
            "message": message,
        },
    }


@dataclass(frozen=True, slots=True)
class QwenLLMProvider(_QwenProviderBase):
    provider_name: str = "qwen_llm"
    supports_native_tool_calling: bool = True

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

    def generate_with_tools(
        self,
        prompt: str,
        *,
        tool_definitions: tuple[Any, ...],
        trace_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ProviderResult:
        qwen_tools = qwen_tools_from_definitions(tool_definitions)
        known_tool_names = tuple(
            tool["function"]["name"]
            for tool in qwen_tools
            if isinstance(tool.get("function"), dict)
            and isinstance(tool["function"].get("name"), str)
        )
        return self._call_tool_decision(
            {
                "prompt": prompt,
                "tools": qwen_tools,
            },
            known_tool_names=known_tool_names,
            trace_id=trace_id,
            metadata=metadata,
        )

    def _call_tool_decision(
        self,
        input_payload: dict[str, Any],
        *,
        known_tool_names: tuple[str, ...],
        trace_id: str | None,
        metadata: dict[str, Any] | None,
    ) -> ProviderResult:
        result_metadata = {
            **dict(metadata or {}),
            "real_provider_requested": True,
            "native_tool_calling": True,
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
            output = qwen_tool_call_to_decision(
                raw_output,
                known_tool_names=known_tool_names,
            )
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

    def _normalize_output(self, output: Any) -> dict[str, Any]:
        if isinstance(output, dict) and self._is_normalized(output):
            return output
        result = {"text": self._message_content(output)}
        language = self._message_language(output)
        if language is not None:
            result["language"] = language
        return result

    def _normalize_content(self, content: str) -> dict[str, Any]:
        return {"text": content}

    @staticmethod
    def _message_language(output: Any) -> str | None:
        try:
            message = output["choices"][0]["message"]
        except (KeyError, IndexError, TypeError):
            return None
        language = message.get("language")
        if isinstance(language, str) and language:
            return language
        annotations = message.get("annotations", ())
        for annotation in annotations:
            if not isinstance(annotation, dict):
                continue
            language = annotation.get("language")
            if isinstance(language, str) and language:
                return language
        return None


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
