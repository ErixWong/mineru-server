from __future__ import annotations

import json
import re
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import httpx

from mineru_mcp.config import MCPConfig, DEFAULT_POSTPROCESS_CONTEXT_SIZE


DEFAULT_SUMMARY_MAX_CHARS = 1200
# Heading-bounded chunks smaller than this are merged with their neighbours to
# avoid one-LLM-call-per-heading on heading-dense documents. Output length grows
# with input length, so keeping merged chunks moderate also bounds completion
# latency and truncation risk. Pass 0 to disable merging entirely.
DEFAULT_MERGE_MIN_CHARS = 8192
DEFAULT_SYSTEM_PROMPT = (
    "你是一个文档后处理助手。"
    "请严格依据用户给定规则处理 markdown 文本，保持原文信息完整，"
    "不要凭空补充事实。"
)
HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
LIST_PATTERN = re.compile(r"^\s*(?:[-*+]\s+|\d+[.)]\s+)")

# Retry policy for the postprocess LLM call: only transient connectivity failures
# (connect errors/timeouts and 5xx responses) are retried. Read/write timeouts are
# deterministic for oversized generation payloads, so retrying just re-burns the
# same cost; 4xx responses, invalid JSON and empty content fail immediately.
LLM_MAX_RETRIES = 2
LLM_RETRY_BACKOFF_BASE = 1.0
LLM_CONNECT_TIMEOUT = 10.0
LLM_READ_TIMEOUT = 600.0
LLM_WRITE_TIMEOUT = 60.0
LLM_POOL_TIMEOUT = 10.0


class PostprocessCancelledError(Exception):
    """Raised when the owning task is cancelled between postprocess chunks."""


@dataclass
class MarkdownBlock:
    kind: str
    text: str
    heading_level: int | None = None
    heading_text: str | None = None

    @property
    def size(self) -> int:
        return len(self.text)


@dataclass
class PostprocessChunk:
    chunk_index: int
    heading_path: list[str]
    text: str
    # Additional heading paths absorbed by small-chunk merging, in document order.
    extra_heading_paths: list[list[str]] = field(default_factory=list)

    @property
    def covered_heading_paths(self) -> list[list[str]]:
        """All heading paths covered by this chunk, consecutive duplicates removed."""
        covered: list[list[str]] = []
        for path in [self.heading_path, *self.extra_heading_paths]:
            if not covered or covered[-1] != path:
                covered.append(path)
        return covered


def normalize_context_size(value: int | None, default_value: int = DEFAULT_POSTPROCESS_CONTEXT_SIZE) -> int:
    if value is None:
        return default_value
    return max(4096, int(value))


def normalize_output_filename(value: str | None) -> str:
    raw = (value or "").strip().replace("\\", "/")
    candidate = Path(raw).name.strip()
    if not candidate:
        raise ValueError("output_filename is required")
    if candidate in {".", ".."}:
        raise ValueError("output_filename is invalid")
    if not candidate.lower().endswith(".md"):
        candidate = f"{candidate}.md"
    return candidate


def build_postprocess_output_path(md_path: Path, output_filename: str | None) -> Path:
    """Build the postprocessed artifact path next to the source markdown.

    The frozen per-task output filename is *required*; there is intentionally no
    derived fallback so that callers who forget to thread the frozen name cannot
    silently diverge into a never-exists default path.
    """
    if not output_filename:
        raise ValueError("postprocess output filename is required")
    return md_path.with_name(normalize_output_filename(output_filename))


def validate_postprocess_output_filename(output_filename: str | None, source_markdown_filename: str) -> str:
    normalized = normalize_output_filename(output_filename)
    if normalized == Path(source_markdown_filename).name:
        raise ValueError("postprocess output filename must differ from the source markdown filename")
    return normalized


def _split_preserving_delimiter(text: str, delimiter: str = "\n\n") -> list[str]:
    if not text:
        return []
    pieces: list[str] = []
    start = 0
    delimiter_length = len(delimiter)
    while True:
        index = text.find(delimiter, start)
        if index == -1:
            pieces.append(text[start:])
            break
        pieces.append(text[start:index + delimiter_length])
        start = index + delimiter_length
    return [piece for piece in pieces if piece]


def _classify_block(block_text: str) -> MarkdownBlock:
    stripped = block_text.lstrip()
    first_line = stripped.splitlines()[0] if stripped.splitlines() else ""
    heading_match = HEADING_PATTERN.match(first_line)
    if heading_match:
        return MarkdownBlock(
            kind="heading",
            text=block_text,
            heading_level=len(heading_match.group(1)),
            heading_text=heading_match.group(2).strip(),
        )
    if stripped.startswith("```"):
        return MarkdownBlock(kind="code", text=block_text)
    if "|" in first_line and len(stripped.splitlines()) >= 2 and set(stripped.splitlines()[1].replace("|", "").strip()) <= {"-", ":", " "}:
        return MarkdownBlock(kind="table", text=block_text)
    if LIST_PATTERN.match(first_line):
        return MarkdownBlock(kind="list", text=block_text)
    return MarkdownBlock(kind="paragraph", text=block_text)


def parse_markdown_blocks(markdown_text: str) -> list[MarkdownBlock]:
    if not markdown_text:
        return []

    blocks: list[MarkdownBlock] = []
    current_lines: list[str] = []
    in_code_block = False

    for line in markdown_text.splitlines(keepends=True):
        stripped = line.strip()
        if stripped.startswith("```"):
            current_lines.append(line)
            in_code_block = not in_code_block
            if not in_code_block:
                blocks.append(_classify_block("".join(current_lines)))
                current_lines = []
            continue

        if in_code_block:
            current_lines.append(line)
            continue

        current_lines.append(line)
        if stripped == "":
            blocks.append(_classify_block("".join(current_lines)))
            current_lines = []

    if current_lines:
        blocks.append(_classify_block("".join(current_lines)))

    return [block for block in blocks if block.text]


def _split_oversized_block(block: MarkdownBlock, context_size: int) -> list[MarkdownBlock]:
    if block.size <= context_size:
        return [block]

    pieces = _split_preserving_delimiter(block.text)
    if len(pieces) <= 1:
        pieces = [block.text[i:i + context_size] for i in range(0, len(block.text), context_size)]

    sub_blocks: list[MarkdownBlock] = []
    buffer = ""
    for piece in pieces:
        if len(piece) > context_size:
            if buffer:
                sub_blocks.append(MarkdownBlock(kind=block.kind, text=buffer, heading_level=block.heading_level, heading_text=block.heading_text))
                buffer = ""
            for start in range(0, len(piece), context_size):
                sub_blocks.append(MarkdownBlock(kind=block.kind, text=piece[start:start + context_size], heading_level=block.heading_level, heading_text=block.heading_text))
            continue
        if len(buffer) + len(piece) <= context_size:
            buffer += piece
        else:
            if buffer:
                sub_blocks.append(MarkdownBlock(kind=block.kind, text=buffer, heading_level=block.heading_level, heading_text=block.heading_text))
            buffer = piece
    if buffer:
        sub_blocks.append(MarkdownBlock(kind=block.kind, text=buffer, heading_level=block.heading_level, heading_text=block.heading_text))
    return sub_blocks


def merge_small_chunks(
    chunks: list[PostprocessChunk],
    context_size: int,
    min_chars: int = DEFAULT_MERGE_MIN_CHARS,
) -> list[PostprocessChunk]:
    """Merge adjacent heading-bounded chunks smaller than ``min_chars``.

    Heading flushes produce one chunk per heading, which explodes the LLM call
    count on heading-dense documents. Adjacent chunks are concatenated (their
    texts are contiguous spans of the source, so concatenation is lossless)
    until the accumulator reaches ``min_chars`` or the next chunk would exceed
    ``context_size``. The absorbed chunks' heading paths are preserved on
    ``extra_heading_paths`` so the prompt can list every covered section.
    """
    if not chunks:
        return []

    def _clone(chunk: PostprocessChunk) -> PostprocessChunk:
        return PostprocessChunk(
            chunk_index=chunk.chunk_index,
            heading_path=list(chunk.heading_path),
            text=chunk.text,
            extra_heading_paths=[list(path) for path in chunk.extra_heading_paths],
        )

    merged: list[PostprocessChunk] = []
    current = _clone(chunks[0])
    for chunk in chunks[1:]:
        fits = len(current.text) + len(chunk.text) <= context_size
        if len(current.text) >= min_chars or not fits:
            merged.append(current)
            current = _clone(chunk)
            continue
        current.text += chunk.text
        current.extra_heading_paths.append(list(chunk.heading_path))
        current.extra_heading_paths.extend(list(path) for path in chunk.extra_heading_paths)
    merged.append(current)

    for index, chunk in enumerate(merged, start=1):
        chunk.chunk_index = index
    return merged


def build_postprocess_chunks(
    markdown_text: str,
    context_size: int,
    min_chunk_chars: int = DEFAULT_MERGE_MIN_CHARS,
) -> list[PostprocessChunk]:
    blocks = parse_markdown_blocks(markdown_text)
    expanded_blocks: list[MarkdownBlock] = []
    for block in blocks:
        expanded_blocks.extend(_split_oversized_block(block, context_size))

    chunks: list[PostprocessChunk] = []
    chunk_text = ""
    heading_stack: list[tuple[int, str]] = []
    current_heading_path: list[str] = []

    def flush_chunk() -> None:
        nonlocal chunk_text
        if not chunk_text:
            return
        chunks.append(
            PostprocessChunk(
                chunk_index=len(chunks) + 1,
                heading_path=list(current_heading_path),
                text=chunk_text,
            )
        )
        chunk_text = ""

    for block in expanded_blocks:
        if block.kind == "heading" and block.heading_level is not None and block.heading_text:
            flush_chunk()
            while heading_stack and heading_stack[-1][0] >= block.heading_level:
                heading_stack.pop()
            heading_stack.append((block.heading_level, block.heading_text))
            current_heading_path = [item[1] for item in heading_stack]

        if chunk_text and len(chunk_text) + block.size > context_size:
            flush_chunk()

        if block.kind != "heading" and not chunk_text and block.size > context_size:
            for sub_block in _split_oversized_block(block, context_size):
                chunks.append(
                    PostprocessChunk(
                        chunk_index=len(chunks) + 1,
                        heading_path=list(current_heading_path),
                        text=sub_block.text,
                    )
                )
            continue

        chunk_text += block.text

    flush_chunk()
    if not chunks and markdown_text:
        chunks = [PostprocessChunk(chunk_index=1, heading_path=[], text=markdown_text)]
    return merge_small_chunks(chunks, context_size, min_chunk_chars)


class TitleLLMPostprocessor:
    def __init__(self, config: MCPConfig):
        self.config = config

    def get_missing_config_fields(self) -> list[str]:
        missing: list[str] = []
        if not (self.config.title_base_url or "").strip():
            missing.append("MINERU_TITLE_BASE_URL")
        if not (self.config.title_api_key or "").strip():
            missing.append("MINERU_TITLE_API_KEY")
        if not (self.config.title_model or "").strip():
            missing.append("MINERU_TITLE_MODEL")
        return missing

    def get_config_error_message(self) -> str:
        missing = self.get_missing_config_fields()
        configured_base_url = (self.config.title_base_url or "").strip() or "<empty>"
        configured_model = (self.config.title_model or "").strip() or "<empty>"
        configured_api_key = "<set>" if (self.config.title_api_key or "").strip() else "<empty>"
        missing_text = ", ".join(missing) if missing else "<none>"
        return (
            "Postprocess LLM configuration is incomplete: "
            f"missing [{missing_text}]. "
            f"Loaded values: MINERU_TITLE_BASE_URL={configured_base_url}, "
            f"MINERU_TITLE_MODEL={configured_model}, "
            f"MINERU_TITLE_API_KEY={configured_api_key}"
        )

    def is_configured(self) -> bool:
        return not self.get_missing_config_fields()

    def process_markdown(
        self,
        markdown_text: str,
        prompt: str,
        context_size: int | None = None,
        cancel_event: Optional[threading.Event] = None,
    ) -> tuple[str, dict[str, Any]]:
        if not self.is_configured():
            raise RuntimeError(self.get_config_error_message())

        effective_context_size = normalize_context_size(context_size, self.config.postprocess_context_size)
        chunks = build_postprocess_chunks(markdown_text, effective_context_size)
        processed_chunks: list[str] = []
        continuity_summary = ""

        with httpx.Client(
            timeout=httpx.Timeout(
                connect=LLM_CONNECT_TIMEOUT,
                read=LLM_READ_TIMEOUT,
                write=LLM_WRITE_TIMEOUT,
                pool=LLM_POOL_TIMEOUT,
            )
        ) as client:
            for index, chunk in enumerate(chunks, start=1):
                if cancel_event is not None and cancel_event.is_set():
                    raise PostprocessCancelledError(
                        f"Postprocess cancelled before chunk {index}/{len(chunks)}"
                    )
                processed_text, continuity_summary = self._process_chunk(
                    client=client,
                    chunk=chunk,
                    prompt=prompt,
                    chunk_index=index,
                    total_chunks=len(chunks),
                    prior_context_summary=continuity_summary,
                )
                processed_chunks.append(processed_text)

        return "\n\n".join(text.strip() for text in processed_chunks if text.strip()).strip(), {
            "context_size": effective_context_size,
            "chunks": len(chunks),
            "source_length": len(markdown_text),
            "strategy": "structured_markdown_chunking",
        }

    def _process_chunk(
        self,
        client: httpx.Client,
        chunk: PostprocessChunk,
        prompt: str,
        chunk_index: int,
        total_chunks: int,
        prior_context_summary: str,
    ) -> tuple[str, str]:
        base_url = (self.config.title_base_url or "").rstrip("/")
        if not base_url:
            raise RuntimeError(self.get_config_error_message())
        headers = {
            "Authorization": f"Bearer {self.config.title_api_key}",
            "Content-Type": "application/json",
        }
        covered_paths = chunk.covered_heading_paths
        if len(covered_paths) <= 1:
            single_path = covered_paths[0] if covered_paths else []
            heading_section = f"当前标题路径：{' > '.join(single_path) if single_path else '<root>'}\n"
        else:
            listing = "\n".join(
                f"{index}. {' > '.join(path) if path else '<root>'}"
                for index, path in enumerate(covered_paths, start=1)
            )
            heading_section = f"当前分片按顺序覆盖以下 {len(covered_paths)} 个标题路径：\n{listing}\n"
        user_prompt = (
            f"后处理规则：\n{prompt.strip()}\n\n"
            f"当前分片：{chunk_index}/{total_chunks}\n"
            f"{heading_section}"
            f"前文连续性摘要：\n{prior_context_summary or '<none>'}\n\n"
            "请仅返回一个 JSON 对象，格式如下：\n"
            '{"processed_markdown":"...","continuity_summary":"..."}\n'
            "其中 processed_markdown 是当前分片后处理后的 markdown 正文；"
            "continuity_summary 是给下一分片使用的连续性摘要，控制在 600 字以内。\n\n"
            "待处理文本如下：\n"
            f"{chunk.text}"
        )
        payload = {
            "model": self.config.title_model,
            "messages": [
                {"role": "system", "content": DEFAULT_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }

        data = self._call_chat_completions(
            client,
            f"{base_url}/chat/completions",
            headers,
            payload,
            chunk_index=chunk_index,
            total_chunks=total_chunks,
        )

        raw_content = self._extract_content(data)
        if not raw_content:
            raise RuntimeError("Title LLM returned empty postprocess content")

        parsed = self._parse_json_content(raw_content)
        if parsed is None:
            raise RuntimeError("Title LLM returned invalid JSON for postprocess chunk")

        processed_markdown = str(parsed.get("processed_markdown", "")).strip()
        continuity_summary = str(parsed.get("continuity_summary", "")).strip()[:DEFAULT_SUMMARY_MAX_CHARS]
        if not processed_markdown:
            raise RuntimeError("Title LLM returned empty processed_markdown")
        return processed_markdown, continuity_summary

    @staticmethod
    def _call_chat_completions(
        client: httpx.Client,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
        chunk_index: int | None = None,
        total_chunks: int | None = None,
    ) -> dict[str, Any]:
        """Call the chat completions endpoint with limited retries.

        Only transient connectivity failures (ConnectError, ConnectTimeout, 5xx)
        are retried. Read/write timeouts for large generation payloads are
        deterministic — retrying just re-burns the same cost.
        """
        for attempt in range(LLM_MAX_RETRIES + 1):
            try:
                response = client.post(url, headers=headers, json=payload)
            except httpx.ConnectTimeout:
                if attempt >= LLM_MAX_RETRIES:
                    chunk_text = f", chunk={chunk_index}/{total_chunks}" if chunk_index and total_chunks else ""
                    raise RuntimeError(
                        f"Postprocess LLM connect timeout: url={url}, model={payload.get('model')}{chunk_text}"
                    ) from None
                time.sleep(LLM_RETRY_BACKOFF_BASE * (2 ** attempt))
                continue
            except httpx.TimeoutException:
                # ReadTimeout / WriteTimeout: the generation is too slow for the
                # payload — retrying the same request won't help.
                chunk_text = f", chunk={chunk_index}/{total_chunks}" if chunk_index and total_chunks else ""
                raise RuntimeError(
                    f"Postprocess LLM timeout: url={url}, model={payload.get('model')}{chunk_text}"
                ) from None
            except httpx.TransportError:
                if attempt >= LLM_MAX_RETRIES:
                    chunk_text = f", chunk={chunk_index}/{total_chunks}" if chunk_index and total_chunks else ""
                    exc = sys.exc_info()[1]
                    raise RuntimeError(
                        f"Postprocess LLM transport error: url={url}, model={payload.get('model')}{chunk_text}, error={type(exc).__name__}: {exc}"
                    ) from None
                time.sleep(LLM_RETRY_BACKOFF_BASE * (2 ** attempt))
                continue
            if response.status_code >= 500:
                if attempt >= LLM_MAX_RETRIES:
                    chunk_text = f", chunk={chunk_index}/{total_chunks}" if chunk_index and total_chunks else ""
                    raise RuntimeError(
                        f"Postprocess LLM server error: url={url}, model={payload.get('model')}, status={response.status_code}{chunk_text}, body={response.text[:500]}"
                    )
                time.sleep(LLM_RETRY_BACKOFF_BASE * (2 ** attempt))
                continue
            response.raise_for_status()
            return response.json()
        # Unreachable: the loop either returns or raises.
        raise RuntimeError("LLM request failed after retries")

    @staticmethod
    def _parse_json_content(raw_content: str) -> Optional[dict[str, Any]]:
        """Parse the LLM JSON payload, tolerating markdown fences and prose padding.

        Local/OpenAI-compatible endpoints often ignore ``response_format`` and wrap
        the JSON object in ```json fences or add stray prose around it. Try the raw
        payload first, then the fenced body, then the outermost {...} span.
        """
        candidates = [raw_content.strip()]

        fence_match = re.search(r"```(?:json)?\s*(.*?)```", raw_content, re.DOTALL)
        if fence_match:
            candidates.append(fence_match.group(1).strip())

        start = raw_content.find("{")
        end = raw_content.rfind("}")
        if start != -1 and end > start:
            candidates.append(raw_content[start:end + 1])

        for candidate in candidates:
            if not candidate:
                continue
            try:
                parsed = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed
        return None

    @staticmethod
    def _extract_content(data: dict[str, Any]) -> str:
        choices = data.get("choices") or []
        if not choices:
            return ""

        message = choices[0].get("message") or {}
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(item.get("text", ""))
            return "".join(parts)
        return ""


def build_postprocess_summary(rule_title: str, metadata: dict[str, Any]) -> str:
    chunks = metadata.get("chunks", 1)
    context_size = metadata.get("context_size", DEFAULT_POSTPROCESS_CONTEXT_SIZE)
    strategy = metadata.get("strategy", "unknown")
    return f"后处理完成：{rule_title}，{chunks} 个分片，上下文窗口 {context_size}，策略 {strategy}"
