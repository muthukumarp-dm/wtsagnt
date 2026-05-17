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
  "reckoner_prompt": "<self-contained prompt for the reckoner (teaching plan) generator>",
  "teaching_tips_prompt": "<self-contained prompt for the teaching-tips generator>",
  "worksheet_prompt": "<self-contained prompt for the student worksheet generator>",
  "teacher_name": "<the teacher's display name if they introduced themselves, e.g. 'Ms. Priya Sharma', else null>"
}}

The five downstream prompts must be self-contained — the downstream agents do
not see this transcript. Restate the subject, grade, topic, learning objectives,
and any constraints the teacher mentioned (visual variety, slide count, etc.).

Teacher-name extraction: only set teacher_name if the transcript clearly contains
a self-introduction such as "I am Ms. X", "from Mr. Y's class", or "for Mrs. Z".
Use the courtesy title the teacher used. If absent or ambiguous, return null.
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
You are a senior teacher producing a **lesson delivery plan** (the "reckoner")
that the teacher will hold in their hand while teaching. This is NOT a
Wikipedia-style fact dump — those are already on Google. This is the structured
teaching aid that makes the lesson land in the classroom.

Brief:
\"\"\"
{reckoner_prompt}
\"\"\"

Respond with ONLY valid JSON (no prose, no markdown fences) matching this schema:
{{
  "title": "...",
  "one_line_summary": "<one sentence capturing the lesson's core idea>",
  "materials": ["...", "..."],
  "timeline": [
    {{"minutes": "0-5 min", "activity": "warm-up: ..."}},
    {{"minutes": "5-15 min", "activity": "..."}}
  ],
  "key_concepts": ["...", "..."],
  "common_misconceptions": ["...", "..."],
  "board_work": ["...", "..."],
  "formative_check": "<one quick check students should pass mid-lesson>"
}}

Constraints:
- materials: 3-6 concrete items the teacher needs (e.g., "Whiteboard markers",
  "Printed worksheet", "Beaker with water"). No filler ("enthusiasm").
- timeline: cover the FULL lesson duration in 4-6 time chunks. Use ranges like
  "0-5 min", "5-15 min". Activities are imperatives ("Show the leaf demo",
  "Have students label the diagram"), not narration.
- key_concepts: 3-5 concise points the lesson must establish.
- common_misconceptions: 2-4 specific things students at this grade get wrong,
  with how to address them.
- board_work: 3-5 things to write/draw on the board, in order.
- formative_check: ONE concrete question, problem, or task that tells the
  teacher whether the class is ready to move on.
- Grade-appropriate language throughout. No filler. Be specific to the topic.
"""


TEACHING_TIPS_GENERATION = """\
You are a senior teacher coach producing concise pedagogy tips for a colleague
who is about to deliver the lesson described in the brief.

Brief:
\"\"\"
{teaching_tips_prompt}
\"\"\"

Respond with ONLY valid JSON (no prose, no markdown fences) matching this schema:
{{
  "tips": [
    {{"heading": "...", "body": "..."}}
  ]
}}

Constraints:
- 3 to 5 tips, each tightly focused on ONE of:
  • common student misconceptions for this topic and how to pre-empt them
  • a sharp engagement hook (real-world example, demo, question to open with)
  • timing / pacing advice for the lesson duration
  • differentiation for fast finishers or struggling students
  • a formative check students should be able to pass mid-lesson
- Each body is 1–2 sentences, plain prose, written teacher-to-teacher
- No filler ("remember to be enthusiastic"), no jargon, no bullet stuffing
- Grade-appropriate — the tips must reflect what students at this grade
  realistically struggle with
"""


WORKSHEET_GENERATION = """\
You are an assessment designer producing a printable one-page worksheet that
students will fill out either in class or as homework. The worksheet must be
tightly tied to the lesson described in the brief — generic Google-able items
are out of scope; this is the reason teachers use us instead of a search.

Brief:
\"\"\"
{worksheet_prompt}
\"\"\"

Respond with ONLY valid JSON (no prose, no markdown fences) matching this schema:
{{
  "title": "<student-facing title>",
  "instructions": "<one-line instructions students read first>",
  "activities": [
    {{
      "kind": "question" | "fill_blank" | "match",
      "prompt": "<the question or task shown to the student>",
      "left_items": ["..."],          // only for kind=match
      "right_items": ["..."],         // only for kind=match (same length as left)
      "answer_hint": "<short note for the teacher, e.g. 'A=3,B=1,C=2' or 'expected: photosynthesis'>"
    }}
  ]
}}

Constraints:
- 5 to 8 activities total
- Mix kinds: include at least one fill_blank, at least one short-answer
  question, and at most one match exercise
- fill_blank prompts MUST contain at least one "___" placeholder
- match: left_items and right_items must have the same length (4-6 pairs);
  the answer_hint shows the correct pairing
- Difficulty matches the grade — fast finishers and strugglers should both
  be able to attempt every activity
- No items that could be answered by Googling the topic without attending
  the lesson — tie wording to the specific concepts the lesson taught
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
