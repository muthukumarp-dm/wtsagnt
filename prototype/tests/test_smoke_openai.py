"""Smoke test: confirm OPENAI_API_KEY works and gpt-4o responds."""
import os
import pytest


@pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY not set",
)
def test_openai_responds():
    from openai import OpenAI

    client = OpenAI()
    response = client.chat.completions.create(
        model="gpt-4o",
        max_tokens=16,
        messages=[{"role": "user", "content": "Reply with exactly the word: ready"}],
    )
    text = response.choices[0].message.content.strip().lower()
    assert "ready" in text
