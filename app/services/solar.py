import json
import re
from collections.abc import AsyncIterator
from typing_extensions import TypedDict

from fastapi import HTTPException
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph

from app import models
from app.config import Settings
from app.schemas import GeneratedDraft


def describe_tone(value: int) -> str:
    if value < 30:
        return "매우 격식 있고 정중한 톤"
    if value < 55:
        return "정중하고 업무적인 톤"
    if value < 75:
        return "중립적이고 자연스러운 톤"
    return "친근하고 따뜻한 톤"


def describe_length(value: int) -> str:
    if value < 30:
        return "핵심만 담은 아주 짧은 길이"
    if value < 60:
        return "짧고 간결한 길이"
    if value < 80:
        return "보통 길이"
    return "상세하고 충분한 설명이 있는 길이"


def build_generation_messages(
    *,
    brief: str,
    tone: int,
    length: int,
    persona: models.Persona | None,
    mail_format: models.MailFormat,
    reply_context: models.ReplyContext | None,
) -> list[dict[str, str]]:
    persona_lines = []
    if persona:
        persona_lines = [
            f"- 이름: {persona.name}",
            f"- 이메일: {persona.email or '(미등록)'}",
            f"- 관계: {persona.relation}",
            f"- 선호 톤: {persona.tone}",
            f"- 메모: {persona.notes}",
            f"- 선호 표현/구조: {persona.prefer}",
            f"- 피해야 할 표현: {persona.avoid}",
            f"- 키워드: {persona.keywords}",
        ]
    reply_lines = []
    if reply_context:
        reply_lines = [
            f"- 보낸 사람: {reply_context.from_addr}",
            f"- 원문 제목: {reply_context.subject}",
            f"- 원문 요약: {reply_context.snippet}",
            f"- 원문 본문:\n{reply_context.raw_body[:4000]}",
        ]
    system = f"""너는 Mello의 한국어 AI 메일 작성 도우미다.
반드시 사용자의 입력과 메일 형식을 반영해서 바로 보낼 수 있는 초안을 작성한다.
출력은 아래 형식을 정확히 따른다.

Subject: <메일 제목>
Body:
<메일 본문>

메일 형식:
- 인사말: {mail_format.greeting}
- 본문 구조: {mail_format.structure}
- 불릿 스타일: {mail_format.bullet_style}
- 마무리 문장: {mail_format.closing}
- 기본 언어: {mail_format.language}
- 서명: {mail_format.signature}

작성 옵션:
- 톤: {describe_tone(tone)}
- 길이: {describe_length(length)}
"""
    user = f"""전달할 내용:
{brief or "(답장 컨텍스트를 바탕으로 답장 초안을 작성)"}

페르소나:
{chr(10).join(persona_lines) if persona_lines else "- 선택 안 됨"}

답장 컨텍스트:
{chr(10).join(reply_lines) if reply_lines else "- 새 메일 작성"}
"""
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


class GenerationGraphState(TypedDict):
    system_prompt: str
    user_prompt: str
    model: str
    api_key: str
    base_url: str
    timeout: float
    raw_text: str


def _chunk_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        pieces: list[str] = []
        for item in content:
            if isinstance(item, str):
                pieces.append(item)
            elif isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if text:
                    pieces.append(str(text))
        return "".join(pieces)
    return str(content) if content else ""


async def _generate_node(state: GenerationGraphState) -> dict[str, str]:
    writer = get_stream_writer()
    model = ChatOpenAI(
        model=state["model"],
        api_key=state["api_key"],
        base_url=state["base_url"].rstrip("/"),
        timeout=state["timeout"],
        temperature=0.7,
        streaming=True,
    )
    messages = [
        SystemMessage(content=state["system_prompt"]),
        HumanMessage(content=state["user_prompt"]),
    ]
    chunks: list[str] = []
    async for chunk in model.astream(messages):
        text = _chunk_text(chunk.content)
        if not text:
            continue
        chunks.append(text)
        writer(text)
    return {"raw_text": "".join(chunks)}


generation_graph = (
    StateGraph(GenerationGraphState)
    .add_node("generate", _generate_node)
    .add_edge(START, "generate")
    .add_edge("generate", END)
    .compile()
)


async def stream_solar_text(settings: Settings, messages: list[dict[str, str]]) -> AsyncIterator[str]:
    if not settings.solar_api_key:
        raise HTTPException(status_code=503, detail="SOLAR_API_KEY가 설정되지 않았습니다.")
    system_prompt = next((item["content"] for item in messages if item["role"] == "system"), "")
    user_prompt = "\n\n".join(item["content"] for item in messages if item["role"] != "system")
    graph_input: GenerationGraphState = {
        "system_prompt": system_prompt,
        "user_prompt": user_prompt,
        "model": settings.solar_model,
        "api_key": settings.solar_api_key,
        "base_url": settings.solar_base_url,
        "timeout": settings.solar_timeout_seconds,
        "raw_text": "",
    }
    try:
        async for token in generation_graph.astream(graph_input, stream_mode="custom"):
            if token:
                yield str(token)
    except HTTPException:
        raise
    except Exception as exc:
        message = str(exc)
        if "rate" in message.lower() or "429" in message:
            raise HTTPException(status_code=429, detail="Solar 요청 한도를 초과했습니다. 잠시 후 다시 시도해주세요.") from exc
        if "timeout" in message.lower():
            raise HTTPException(status_code=504, detail="Solar 응답 시간이 초과되었습니다.") from exc
        raise HTTPException(status_code=502, detail="Solar 생성 요청에 실패했습니다.") from exc


def parse_generated_draft(text: str) -> GeneratedDraft:
    cleaned = text.strip()
    json_text = cleaned
    fence = re.search(r"```(?:json)?\s*(.*?)```", cleaned, flags=re.DOTALL)
    if fence:
        json_text = fence.group(1).strip()
    try:
        payload = json.loads(json_text)
        if isinstance(payload, dict):
            subject = str(payload.get("subject") or payload.get("Subject") or "")
            body = str(payload.get("body") or payload.get("Body") or "")
            if subject or body:
                return GeneratedDraft(subject=subject.strip(), body=body.strip())
    except json.JSONDecodeError:
        pass

    marker = re.search(
        r"(?:^|\n)\s*(?:Subject|제목)\s*:\s*(?P<subject>.*?)\s*(?:\n+)\s*(?:Body|본문)\s*:\s*(?P<body>.*)",
        cleaned,
        flags=re.DOTALL | re.IGNORECASE,
    )
    if marker:
        return GeneratedDraft(
            subject=marker.group("subject").strip(),
            body=marker.group("body").strip(),
        )

    lines = [line.strip() for line in cleaned.splitlines()]
    nonempty = [line for line in lines if line]
    if not nonempty:
        return GeneratedDraft(subject="", body="")
    first = re.sub(r"^(Subject|제목)\s*:\s*", "", nonempty[0], flags=re.IGNORECASE)
    body = "\n".join(lines[1:]).strip() if len(lines) > 1 else first
    return GeneratedDraft(subject=first[:120], body=body)
