"""
ChannelOS — ScriptWriter
Turns a scored idea dict into a complete spoken script (55-70 words, ~30s).
"""

import os
import json

try:
    from anthropic import Anthropic
except ImportError:
    Anthropic = None  # type: ignore


def write_script(idea: dict, language: str) -> tuple[dict, object]:
    """
    Returns (script_dict, anthropic_message) — message returned for cost tracking.

    script_dict keys:
      spoken_text, caption, hashtags, screen_items
    """
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    fmt = idea.get("format", "single")

    format_guidance = {
        "ranking": (
            "FORMAT = RANKING. Structure the script as a countdown using "
            "these items: " + json.dumps(idea.get("list_items", [])) + ". "
            "Count UP toward the best (e.g. 'Number 3… Number 2… and number 1'). "
            "Tease that #1 is the best so viewers stay. Each item gets one punchy line."
        ),
        "versus": (
            "FORMAT = VERSUS. Compare: "
            + json.dumps(idea.get("versus", {})) + ". "
            "Set up the matchup, 1-2 points each, declare winner at the end."
        ),
        "single": "FORMAT = SINGLE. Deep dive on one story/tool. Follow the structure beats.",
    }.get(fmt, "FORMAT = SINGLE.")

    prompt = f"""You are a short-form video scriptwriter. Turn this idea into a
complete spoken script for a ~30-second faceless {language} TikTok/Reels video.

IDEA:
- Title: {idea['title']}
- Hook: {idea['hook']}
- Angle: {idea['angle']}
- Structure beats: {json.dumps(idea.get('structure', []))}
- Affiliate angle: {idea.get('affiliate_angle', '')}

{format_guidance}

Rules:
- Open with the EXACT hook provided
- 55-70 words TOTAL (hard limit — short = higher retention)
- You may reference relevant tools by name where they genuinely fit the content, but do NOT claim to provide links to them or imply the viewer gets anything free. Real affiliate links are added separately at publish time — your job is honest, useful content, not selling.
- End with a light, HONEST CTA: either engagement ("follow for a daily AI tool", "which one would you try first?") OR "tools in bio" ONLY as a soft pointer. NEVER invent a freebie that doesn't exist: no "free checklist", "free guide", "free template", "download", "DM me" — these resources do NOT exist and promising them is a false promise. Do not promise to send or link anything specific.
- Stay factual and brand-safe

Return ONLY valid JSON, no markdown:
{{
  "spoken_text": "the full voiceover text, hook first",
  "caption": "the post caption",
  "hashtags": ["#...", "#..."],
  "screen_items": ["short on-screen labels matching the format"]
}}"""

    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1200,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = msg.content[0].text.strip().replace("```json", "").replace("```", "").strip()
    return json.loads(raw), msg
