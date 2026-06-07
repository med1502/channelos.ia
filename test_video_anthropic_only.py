"""
ChannelOS — Test MVP (ANTHROPIC-ONLY) — v4 (clean)
==================================================
Corrige le chevauchement des sous-titres :
  • UN seul sous-titre affiché à la fois (timing strict, sans overlap)
  • Sous-titres courts : MAX 3 mots (vrai standard TikTok)
  • Timing calibré sur les syllabes + lead-in
  • Police Poppins si dispo, sinon DejaVu

Seule clé requise : ANTHROPIC_API_KEY
"""

import os
import re
import sys
import json
import wave
import textwrap
import subprocess

# ─────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────
NICHE = sys.argv[1] if len(sys.argv) > 1 else "AI tools for entrepreneurs"
LANGUAGE = "EN"
OUTPUT_DIR = "output"
W, H = 1080, 1920

PIPER_BIN = "piper_bin/piper/piper"
PIPER_LIBS = "./piper_bin/piper"
PIPER_MODEL = "voices/en_US-ryan-medium.onnx"
PIPER_LENGTH_SCALE = "1.1"  # 10% plus lent = débit plus posé

LEAD = 0.15  # le texte apparait 150ms avant la voix

# Police : "Poppins-Bold" si installée, sinon "DejaVu-Sans-Bold"
FONT = "Poppins-Bold"

os.makedirs(OUTPUT_DIR, exist_ok=True)


# ─────────────────────────────────────────────────────────
# ÉTAPE 1 — SCRIPT via Claude
# ─────────────────────────────────────────────────────────
def generate_script(niche: str, language: str) -> dict:
    from anthropic import Anthropic

    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    prompt = f"""Write a short-form video script for a faceless {language} TikTok/Reels video.
Niche: {niche}

Requirements:
- Total spoken length: ~40 seconds (about 100-115 words)
- Punchy hook in the first sentence (must stop the scroll)
- 3-4 short value-packed sentences in the body
- A clear CTA at the end mentioning "link in bio"
- Tone: energetic, direct, no fluff

Return ONLY valid JSON, no markdown, no preamble:
{{
  "hook": "...",
  "body": "...",
  "cta": "...",
  "caption": "...",
  "hashtags": ["...", "..."],
  "subtitles": ["max 3 words", "max 3 words", "..."]
}}

CRITICAL for "subtitles":
- Cover the FULL spoken text (hook + body + cta), in order
- Use the EXACT words spoken (no paraphrase)
- MAX 3 WORDS per subtitle line (this is mandatory for TikTok-style captions)
- Many short lines is GOOD — aim for punchy, fast-reading chunks"""

    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = msg.content[0].text.strip()
    raw = raw.replace("```json", "").replace("```", "").strip()
    return json.loads(raw)


# ─────────────────────────────────────────────────────────
# ÉTAPE 2 — VOIX OFF via Piper TTS
# ─────────────────────────────────────────────────────────
def generate_voiceover(script: dict, out_wav: str) -> str:
    full_text = f"{script['hook']} {script['body']} {script['cta']}"

    if not os.path.exists(PIPER_MODEL):
        raise FileNotFoundError(f"Modèle Piper introuvable : {PIPER_MODEL}")

    env = os.environ.copy()
    env["LD_LIBRARY_PATH"] = PIPER_LIBS
    proc = subprocess.run(
        [PIPER_BIN, "--model", PIPER_MODEL,
         "--length_scale", PIPER_LENGTH_SCALE,
         "--output_file", out_wav],
        input=full_text.encode("utf-8"),
        capture_output=True,
        env=env,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"Piper a échoué : {proc.stderr.decode()}")
    return out_wav


def wav_duration(path: str) -> float:
    with wave.open(path, "rb") as w:
        return w.getnframes() / float(w.getframerate())


# ─────────────────────────────────────────────────────────
# TIMING — calibré syllabes, SANS chevauchement
# ─────────────────────────────────────────────────────────
def compute_timings(subs, total):
    """
    Retourne [(texte, start, end)] où chaque sous-titre se termine
    EXACTEMENT quand le suivant commence. Un seul texte à l'écran.
    """
    def syllables(text):
        return max(len(re.findall(r"[aeiouyAEIOUY]+", text)), 1)

    weights = [syllables(s) for s in subs]
    total_w = sum(weights)

    # Points de bascule cumulés
    boundaries = [0.0]
    cursor = 0.0
    for w in weights:
        cursor += total * (w / total_w)
        boundaries.append(cursor)

    timings = []
    for i, sub in enumerate(subs):
        start = max(boundaries[i] - LEAD, 0.0)
        end = boundaries[i + 1] - LEAD
        if end <= start:
            end = start + 0.3
        timings.append((sub, start, end))
    return timings


# ─────────────────────────────────────────────────────────
# ÉTAPE 3 — ASSEMBLAGE VIDÉO
# ─────────────────────────────────────────────────────────
def build_video(script: dict, audio_path: str, out_path: str):
    from moviepy.editor import (
        AudioFileClip, ColorClip, TextClip, CompositeVideoClip,
    )

    audio = AudioFileClip(audio_path)
    duration = audio.duration

    subs = script.get("subtitles", [])
    if not subs:
        subs = textwrap.wrap(
            f"{script['hook']} {script['body']} {script['cta']}", width=18
        )

    # Sécurité : re-découper tout sous-titre de plus de 3 mots
    clean_subs = []
    for s in subs:
        words = s.split()
        for i in range(0, len(words), 3):
            clean_subs.append(" ".join(words[i:i + 3]))
    subs = clean_subs

    timed = compute_timings(subs, duration)

    bg = ColorClip(size=(W, H), color=(13, 17, 23)).set_duration(duration)
    layers = [bg]

    for line, start, end in timed:
        seg_dur = max(end - start, 0.3)
        txt = TextClip(
            line.upper(),
            fontsize=110,
            color="white",
            font=FONT,
            method="caption",
            size=(W - 160, None),
            stroke_color="black",
            stroke_width=6,
            align="center",
        )
        txt = (
            txt.set_start(start)
            .set_duration(seg_dur)
            .set_position("center")
        )
        layers.append(txt)

    # Barre de progression cyan en bas (crop dynamique, pas de resize)
    full_bar = ColorClip(size=(W, 10), color=(0, 212, 255)).set_duration(duration)

    def crop_bar(get_frame, t):
        frame = get_frame(t).copy()
        w_visible = max(int(W * t / duration), 1)
        frame[:, w_visible:] = (13, 17, 23)
        return frame

    progress = full_bar.fl(crop_bar, apply_to=[]).set_position(("left", H - 80))
    layers.append(progress)

    final = CompositeVideoClip(layers, size=(W, H)).set_audio(audio)
    final.write_videofile(
        out_path,
        fps=30,
        codec="libx264",
        audio_codec="aac",
        preset="medium",
        threads=4,
    )


# ─────────────────────────────────────────────────────────
# PIPELINE
# ─────────────────────────────────────────────────────────
def main():
    print(f"\n🎬 ChannelOS Test v4 — '{NICHE}' ({LANGUAGE})\n")

    print("① Script via Claude...")
    script = generate_script(NICHE, LANGUAGE)
    print(f"   Hook: {script['hook']}\n")
    with open(f"{OUTPUT_DIR}/script.json", "w") as f:
        json.dump(script, f, indent=2, ensure_ascii=False)

    print("② Voix off via Piper (length_scale=%s)..." % PIPER_LENGTH_SCALE)
    audio_path = generate_voiceover(script, f"{OUTPUT_DIR}/voice.wav")
    print(f"   Audio: {audio_path}  ({wav_duration(audio_path):.1f}s)\n")

    print("③ Assemblage synchronisé...")
    video_path = f"{OUTPUT_DIR}/video.mp4"
    build_video(script, audio_path, video_path)

    print(f"\n✅ Terminé !  🎥 {video_path}")
    print(f"👉 ffplay {video_path}\n")


if __name__ == "__main__":
    main()