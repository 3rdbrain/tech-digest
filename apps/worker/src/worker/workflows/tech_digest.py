"""Hacker News tech digest: fetch the front page, keep tech-industry stories, email a summary with a podcast-style audio briefing."""

import asyncio
import base64
import datetime as dt
from html import escape

import pydantic
import mistralai.workflows as workflows
from mistralai.workflows import Depends
from mistralai.workflows.plugins.mistralai import (
    ChatCompletionRequest,
    UserMessage,
    chat_parse_to_model,
    get_mistral_client,
)
from mistralai.workflows.plugins.mistralai.connectors import (
    ToolCallClient,
    connector,
    uses_connectors,
)

gmail = connector("gmail")

DEFAULT_RECIPIENT = "pravinboppuri@gmail.com"
HN_TOP_STORIES_URL = "https://hacker-news.firebaseio.com/v0/topstories.json"
HN_ITEM_URL = "https://hacker-news.firebaseio.com/v0/item/{story_id}.json"
TTS_MODEL = "voxtral-mini-tts-3-0"
TTS_VOICE = "gb_jane_neutral"
DEFAULT_MAX_STORIES = 10
MAX_ATTACHMENT_B64_CHARS = 3_900_000


class Story(pydantic.BaseModel):
    story_id: int
    title: str
    url: str
    by: str = ""
    score: int = 0
    comments: int = 0
    posted_at: str = ""


class DigestItem(pydantic.BaseModel):
    title: str
    url: str
    category: str
    one_liner: str


class Digest(pydantic.BaseModel):
    items: list[DigestItem]


class _Script(pydantic.BaseModel):
    script: str


class DigestInput(pydantic.BaseModel):
    recipient: str | None = None
    max_stories: int = DEFAULT_MAX_STORIES


class DigestOutput(pydantic.BaseModel):
    subject: str
    recipient: str
    items: list[DigestItem]
    audio_bytes: int
    email_message_id: str | None = None


@workflows.activity(start_to_close_timeout=dt.timedelta(seconds=60))
async def fetch_hn_front_page(max_stories: int) -> list[Story]:
    import httpx

    async with httpx.AsyncClient(timeout=20.0) as http:
        ids_response = await http.get(HN_TOP_STORIES_URL)
        ids_response.raise_for_status()
        story_ids = ids_response.json()[: max(0, max_stories) * 2]

        async def _fetch(story_id: int) -> Story | None:
            response = await http.get(HN_ITEM_URL.format(story_id=story_id))
            response.raise_for_status()
            data = response.json()
            if not data or data.get("dead") or data.get("type") != "story":
                return None
            return Story(
                story_id=data["id"],
                title=data.get("title", ""),
                url=data.get("url", f"https://news.ycombinator.com/item?id={story_id}"),
                by=data.get("by", ""),
                score=data.get("score", 0),
                comments=data.get("descendants", 0),
                posted_at=dt.datetime.fromtimestamp(
                    data.get("time", 0), tz=dt.timezone.utc
                ).isoformat(),
            )

        stories = await asyncio.gather(*(_fetch(sid) for sid in story_ids))
    return [story for story in stories if story is not None and story.title][
        : max(0, max_stories)
    ]


@workflows.activity(start_to_close_timeout=dt.timedelta(seconds=120))
async def curate_tech_stories(stories: list[Story]) -> Digest:
    if not stories:
        return Digest(items=[])
    listing = "\n".join(
        f"- {index + 1}. {story.title} (score {story.score}, {story.comments} comments) {story.url}"
        for index, story in enumerate(stories)
    )
    request = ChatCompletionRequest(
        model="mistral-small-latest",
        messages=[
            UserMessage(
                content=(
                    "You are the editor of a daily technology-industry newsletter. "
                    "Below are stories from the Hacker News front page. "
                    "Keep only stories about the tech industry: companies, products, "
                    "startups, funding, AI models and infrastructure, semiconductors, "
                    "developer tools, cybersecurity, and tech policy or regulation. "
                    "Drop personal blogs, essays, life advice, career posts, ask-HN "
                    "discussions, and anything not about the technology industry. "
                    "Keep at most 10 stories, ranked by relevance to the tech industry. "
                    "For each kept story write a one-sentence, factual one-liner summary. "
                    "Use the story's original title verbatim. If nothing qualifies, "
                    "return an empty list.\n\n"
                    f"Stories:\n{listing}"
                )
            )
        ],
    )
    return await chat_parse_to_model(Digest, request)


@workflows.activity(start_to_close_timeout=dt.timedelta(seconds=120))
async def write_podcast_script(digest: Digest) -> str:
    if not digest.items:
        return (
            "Hi, this is your Tech Digest. The Hacker News front page today has no "
            "major tech-industry stories, so there is nothing to cover. See you next time."
        )
    listing = "\n".join(f"- {item.title}: {item.one_liner}" for item in digest.items)
    request = ChatCompletionRequest(
        model="mistral-small-latest",
        messages=[
            UserMessage(
                content=(
                    "You are the host of a daily tech-news micro podcast. Write a "
                    "warm, energetic spoken script presenting today's headlines from "
                    "the list below. Rules: natural spoken prose, 2 to 4 sentences per "
                    "story, no markdown, no lists, no stage directions, no emojis, no "
                    "sound effects. Open with a short greeting and close with a "
                    "one-sentence sign-off. The whole script must stay under 300 words "
                    "so it reads aloud in under two minutes.\n\n"
                    f"Headlines:\n{listing}"
                )
            )
        ],
    )
    parsed = await chat_parse_to_model(_Script, request)
    return parsed.script.strip()


@workflows.activity(start_to_close_timeout=dt.timedelta(seconds=180))
async def synthesize_podcast_audio(script: str) -> str:
    client = get_mistral_client()
    speech = await client.audio.speech.complete_async(
        model=TTS_MODEL,
        input=script,
        voice_id=TTS_VOICE,
        response_format="mp3",
    )
    return speech.audio_data


def _render_digest_html(digest: Digest, date_label: str) -> str:
    rows = "".join(
        f"<tr><td style='padding:8px 0;border-bottom:1px solid #e5e7eb;'>"
        f"<div style='font-size:15px;font-weight:600;'>{escape(item.title)}</div>"
        f"<div style='color:#4b5563;font-size:13px;margin-top:2px;'>"
        f"{escape(item.one_liner)}</div>"
        f"<div style='color:#9ca3af;font-size:11px;margin-top:2px;'>"
        f"{escape(item.category)} &middot; <a href='{escape(item.url)}'>link</a>"
        f"</div></td></tr>"
        for item in digest.items
    )
    return (
        "<div style='font-family:Arial,Helvetica,sans-serif;max-width:640px;'>"
        f"<h2 style='margin:0 0 4px;'>Tech Digest &mdash; {escape(date_label)}</h2>"
        "<p style='color:#6b7280;font-size:12px;margin:0 0 12px;'>"
        "Latest tech-industry news from the Hacker News front page. "
        "The podcast audio briefing is attached to this email.</p>"
        f"<table style='border-collapse:collapse;width:100%;'>{rows}</table></div>"
    )


def _render_digest_text(digest: Digest, date_label: str) -> str:
    lines = [f"Tech Digest — {date_label}", ""]
    lines += [
        f"{index + 1}. {item.title}\n   {item.one_liner}\n   {item.url}"
        for index, item in enumerate(digest.items)
    ]
    lines.append("\nPodcast audio briefing attached (tech-digest-podcast.mp3).")
    return "\n".join(lines)


def audio_attachment(audio_b64: str) -> dict | None:
    """The MP3 attachment entry, or None when it would exceed Gmail's limit."""
    if len(audio_b64) > MAX_ATTACHMENT_B64_CHARS:
        return None
    return {
        "content": audio_b64,
        "filename": "tech-digest-podcast.mp3",
        "mimeType": "audio/mpeg",
    }


@workflows.activity(start_to_close_timeout=dt.timedelta(seconds=60))
async def send_digest_email(
    recipient: str,
    subject: str,
    digest_html: str,
    digest_text: str,
    audio_b64: str,
    client: ToolCallClient = Depends(gmail),
) -> str | None:
    arguments: dict = {
        "to": [recipient],
        "subject": subject,
        "body": digest_text,
        "htmlBody": digest_html,
    }
    attachment = audio_attachment(audio_b64)
    if attachment is not None:
        arguments["attachments"] = [attachment]
    result = await client.call_tool(tool_name="send_email", arguments=arguments)
    return result.get("id") if isinstance(result, dict) else None


@workflows.workflow.define(name="hn-tech-digest", on_behalf_of=True)
@uses_connectors(gmail)
class HNTechDigestWorkflow:
    @workflows.workflow.entrypoint
    async def run(self, data: DigestInput) -> DigestOutput:
        recipient = data.recipient or DEFAULT_RECIPIENT
        stories = await fetch_hn_front_page(data.max_stories)
        digest = await curate_tech_stories(stories)
        script = await write_podcast_script(digest)
        audio_b64 = await synthesize_podcast_audio(script)
        if len(audio_b64) > MAX_ATTACHMENT_B64_CHARS:
            sentences = script.split(". ")
            script = ". ".join(sentences[: max(1, len(sentences) // 2)]) + "."
            audio_b64 = await synthesize_podcast_audio(script)

        date_label = workflows.workflow.now().strftime("%A, %d %B %Y")
        subject = f"Tech Digest — {date_label}"
        message_id = await send_digest_email(
            recipient=recipient,
            subject=subject,
            digest_html=_render_digest_html(digest, date_label),
            digest_text=_render_digest_text(digest, date_label),
            audio_b64=audio_b64,
        )
        return DigestOutput(
            subject=subject,
            recipient=recipient,
            items=digest.items,
            audio_bytes=len(base64.b64decode(audio_b64)),
            email_message_id=message_id,
        )
