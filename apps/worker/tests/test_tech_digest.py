"""Rendering and attachment-size behavior of the tech digest email."""

import base64

from worker.workflows.tech_digest import (
    MAX_ATTACHMENT_B64_CHARS,
    Digest,
    DigestItem,
    _render_digest_html,
    _render_digest_text,
    audio_attachment,
)


def _digest() -> Digest:
    return Digest(
        items=[
            DigestItem(
                title="Acme <buys> Beta",
                url="https://example.com/article",
                category="M&A",
                one_liner="Acme acquires Beta for $1B & change.",
            ),
            DigestItem(
                title="Chips get faster",
                url="https://example.com/chips",
                category="Semiconductors",
                one_liner="A new fab opens.",
            ),
        ]
    )


def test_html_escapes_model_output_and_links() -> None:
    html = _render_digest_html(_digest(), "Monday, 01 January 2025")
    assert "Acme &lt;buys&gt; Beta" in html
    assert "acquires Beta for $1B &amp; change" in html
    assert "href='https://example.com/article'" in html


def test_text_lists_every_item_with_url() -> None:
    text = _render_digest_text(_digest(), "Monday, 01 January 2025")
    assert "1. Acme <buys> Beta" in text
    assert "https://example.com/chips" in text
    assert "tech-digest-podcast.mp3" in text


def test_audio_attachment_respects_size_limit() -> None:
    small = base64.b64encode(b"fake-mp3-bytes").decode()
    attached = audio_attachment(small)
    assert attached is not None
    assert attached["mimeType"] == "audio/mpeg"
    assert attached["filename"] == "tech-digest-podcast.mp3"
    oversized = base64.b64encode(b"x" * (MAX_ATTACHMENT_B64_CHARS - 4)).decode()
    assert audio_attachment(oversized) is None
