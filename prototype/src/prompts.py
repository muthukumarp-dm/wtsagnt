"""Prompt templates for the LLM calls in the pipeline.

Each constant is the FULL prompt sent to the model. {placeholders} are filled
in by pipeline.py at call time.
"""
from __future__ import annotations


INTENT_AND_PROMPT_ENGINEERING = """\
You are a curriculum design assistant. A teacher has sent a transcript
describing what they need for an upcoming class. Your job is to:

1. Extract the structured intent (subject, grade, topic, duration, output counts)
2. Compose three downstream prompts for specialist agents (PPT, MCQ, reckoner)

Input transcript:
\"\"\"
{transcript}
\"\"\"

Respond with ONLY valid JSON matching this schema (no prose, no markdown fences):
{{
  "subject": "...",
  "grade": "...",
  "topic": "...",
  "duration_min": <int>,
  "n_slides": <int recommended content-slide count, excluding MCQ slides>,
  "n_mcqs": <int>,
  "ppt_prompt": "<self-contained prompt for the PPT content generator>",
  "mcq_prompt": "<self-contained prompt for the MCQ generator>",
  "reckoner_prompt": "<self-contained prompt for the reckoner generator>"
}}

The three downstream prompts must be self-contained — the downstream agents do
not see this transcript. Restate the subject, grade, topic, learning objectives,
and any constraints the teacher mentioned (visual variety, slide count, etc.).
"""


PPT_CONTENT_GENERATION = """\
You are an instructional designer building a slide deck for a classroom lesson.

Brief:
\"\"\"
{ppt_prompt}
\"\"\"

Respond with ONLY valid JSON (no prose, no markdown fences) matching this schema:
{{
  "slides": [
    {{
      "layout": "title" | "bullets" | "two_column" | "image_text",
      "title": "...",
      "subtitle": "..." | null,
      "bullets": ["...", "..."] | null,
      "left_column": "..." | null,
      "right_column": "..." | null,
      "body": "..." | null
    }}
  ]
}}

Constraints:
- Start with one "title" slide
- Vary layouts across the deck — do NOT use only "bullets". Mix bullets, two_column, image_text.
- No more than 5 bullets per "bullets" slide
- Use grade-appropriate language
- Aim for the slide count specified in the brief
"""


MCQ_GENERATION = """\
You are an assessment designer building multiple-choice questions for a classroom quiz.

Brief:
\"\"\"
{mcq_prompt}
\"\"\"

Respond with ONLY valid JSON (no prose, no markdown fences) matching this schema:
{{
  "mcqs": [
    {{
      "question": "...",
      "options": ["...", "...", "...", "..."],
      "answer": "A" | "B" | "C" | "D",
      "explanation": "..."
    }}
  ]
}}

Constraints:
- EXACTLY 4 options per question, in A B C D order
- Cover different cognitive levels (recall, understanding, application)
- Distractors must be plausible, not silly
- Questions must be answerable from the lesson content, not require outside knowledge
- One-sentence explanation per MCQ
"""


RECKONER_GENERATION = """\
You are a curriculum writer producing a one-page handout that students can take
home as a quick reference for the lesson.

Brief:
\"\"\"
{reckoner_prompt}
\"\"\"

Respond with ONLY valid JSON (no prose, no markdown fences) matching this schema:
{{
  "title": "...",
  "sections": [
    {{"heading": "...", "body": "..."}}
  ]
}}

Constraints:
- 3 to 6 sections
- Each section body is 1–3 sentences, no longer
- Use grade-appropriate language
- The whole handout should fit on one printed A4 page when rendered
"""


REVISION_MERGER = """\
You are reconciling a teacher's request with revisions they sent later.

ORIGINAL REQUEST:
\"\"\"
{original_request}
\"\"\"

REVISIONS (in order, latest takes precedence on conflicts):
\"\"\"
{revisions_text}
\"\"\"

Produce a SINGLE coherent revised brief that incorporates the revisions into
the original. Resolve conflicts in favor of the latest revision.

Output requirements:
- Plain prose, the way a teacher would write it
- No JSON, no markdown, no preamble like "Here is..."
- The intent agent will consume your output as if it were the teacher's
  original request — make it readable as a standalone instruction
"""


REPLY_PARSER_HAIKU = """\
Classify a teacher's WhatsApp reply.

Context: the teacher received a summary of an auto-generated lesson and was
asked to either approve it (to receive the files) or describe changes they want.

Reply: \"\"\"{body}\"\"\"

Output EXACTLY one word, no punctuation, no explanation:
APPROVED | CHANGES | UNCLEAR

- APPROVED: the reply means yes / send the files
- CHANGES: the reply describes modifications to the lesson
- UNCLEAR: the reply is too short, contradictory, or off-topic to decide
"""
