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
from app.generation_options import PERSONA_TONES, generation_length_description, generation_tone_description
from app.schemas import GeneratedDraft
from app.schemas import PersonaStructureOut


def describe_tone(value: int) -> str:
    return generation_tone_description(value)


def describe_length(value: int) -> str:
    return generation_length_description(value)


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

검증 규칙:
- 페르소나의 피해야 할 표현을 제목이나 본문에 그대로 사용하지 않는다.
- 서명이 제공되면 본문 마지막에 서명을 포함한다.

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


def _normalize_for_match(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def _policy_lines(value: str | None) -> list[str]:
    if not value:
        return []
    items: list[str] = []
    for raw in re.split(r"[\n,]", value):
        item = raw.strip()
        if item and item not in items:
            items.append(item)
    return items


def _ensure_signature(body: str, signature: str) -> str:
    clean_signature = signature.strip()
    if not clean_signature:
        return body.strip()
    normalized_body = _normalize_for_match(body)
    normalized_signature = _normalize_for_match(clean_signature)
    if normalized_signature and normalized_signature in normalized_body:
        return body.strip()
    return f"{body.strip()}\n\n{clean_signature}"


def _forbidden_terms_in_draft(draft: GeneratedDraft, persona: models.Persona | None) -> list[str]:
    if not persona:
        return []
    haystack = _normalize_for_match(f"{draft.subject}\n{draft.body}")
    found: list[str] = []
    for term in _policy_lines(persona.avoid):
        normalized = _normalize_for_match(term)
        if normalized and normalized in haystack:
            found.append(term)
    return found


def apply_generation_guardrails(
    draft: GeneratedDraft,
    *,
    persona: models.Persona | None,
    mail_format: models.MailFormat,
    forbidden_status_code: int = 502,
    forbidden_target: str = "생성 결과",
    forbidden_action: str = "다시 생성해주세요.",
) -> GeneratedDraft:
    guarded = GeneratedDraft(
        subject=draft.subject.strip(),
        body=_ensure_signature(draft.body, mail_format.signature),
    )
    forbidden_terms = _forbidden_terms_in_draft(guarded, persona)
    if forbidden_terms:
        preview = ", ".join(forbidden_terms[:3])
        raise HTTPException(
            status_code=forbidden_status_code,
            detail=f"{forbidden_target}에 피해야 할 표현이 포함되었습니다: {preview}. {forbidden_action}",
        )
    return guarded


def _trim_list(value: object, *, limit: int = 6) -> list[str]:
    if isinstance(value, str):
        raw_items = re.split(r"[\n,]", value)
    elif isinstance(value, list):
        raw_items = value
    else:
        raw_items = []
    items: list[str] = []
    for item in raw_items:
        text = str(item).strip()
        if text and text not in items:
            items.append(text[:40])
        if len(items) >= limit:
            break
    return items


def _normalize_persona_tone(value: object) -> str:
    tone = str(value or "").strip()
    if tone in PERSONA_TONES:
        return tone
    if "매우" in tone and any(keyword in tone for keyword in ("격식", "정중", "공식")):
        return "매우 격식"
    if "매우" in tone and any(keyword in tone for keyword in ("친근", "캐주얼", "편한")):
        return "매우 친근"
    if any(keyword in tone for keyword in ("격식", "정중", "공손", "예의", "공식")):
        return "격식"
    if any(keyword in tone for keyword in ("친근", "따뜻", "편한", "캐주얼", "친구", "가족")):
        return "친근"
    return "중립"


def parse_persona_structure(text: str) -> PersonaStructureOut:
    cleaned = text.strip()
    json_text = cleaned
    fence = re.search(r"```(?:json)?\s*(.*?)```", cleaned, flags=re.DOTALL)
    if fence:
        json_text = fence.group(1).strip()
    try:
        payload = json.loads(json_text)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=502, detail="페르소나 분석 결과를 해석하지 못했습니다.") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=502, detail="페르소나 분석 결과를 해석하지 못했습니다.")

    return PersonaStructureOut(
        tone=_normalize_persona_tone(payload.get("tone")),
        keywords=_trim_list(payload.get("keywords")),
        avoid=_trim_list(payload.get("avoid")),
        prefer=str(payload.get("prefer") or "").strip()[:500],
        notes=str(payload.get("notes") or "").strip()[:1000],
    )


async def structure_persona_text(settings: Settings, text: str) -> PersonaStructureOut:
    if not settings.solar_api_key:
        raise HTTPException(status_code=503, detail="SOLAR_API_KEY가 설정되지 않았습니다.")
    model = ChatOpenAI(
        model=settings.solar_model,
        api_key=settings.solar_api_key,
        base_url=settings.solar_base_url.rstrip("/"),
        timeout=settings.solar_timeout_seconds,
        temperature=0.2,
    )
    messages = [
        SystemMessage(
            content=(
                "너는 메일 수신자 페르소나 메모를 구조화하는 도우미다. "
                "반드시 JSON만 출력한다. "
                "스키마: {\"tone\":\"매우 격식|격식|중립|친근|매우 친근\","
                "\"keywords\":[\"키워드\"],\"avoid\":[\"피해야 할 표현\"],"
                "\"prefer\":\"선호하는 메일 구조\",\"notes\":\"요약 메모\"}. "
                "값이 불명확하면 tone은 중립, 배열은 빈 배열로 둔다."
            )
        ),
        HumanMessage(content=f"수신자 메모:\n{text[:4000]}"),
    ]
    try:
        response = await model.ainvoke(messages)
    except HTTPException:
        raise
    except Exception as exc:
        message = str(exc)
        if "rate" in message.lower() or "429" in message:
            raise HTTPException(status_code=429, detail="Solar 요청 한도를 초과했습니다. 잠시 후 다시 시도해주세요.") from exc
        if "timeout" in message.lower():
            raise HTTPException(status_code=504, detail="Solar 응답 시간이 초과되었습니다.") from exc
        raise HTTPException(status_code=502, detail="페르소나 분석 요청에 실패했습니다.") from exc
    return parse_persona_structure(_chunk_text(response.content))
