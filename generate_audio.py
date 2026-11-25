# -*- coding: utf-8 -*-
'''Generate pre-recorded Neural AI MP3 voice clips for Flamboyant Speaking Lab using edge-tts.'''

import asyncio
import json
import re
from pathlib import Path
import edge_tts

ROOT = Path(__file__).resolve().parent
HTML_PATH = ROOT / "index.html"
AUDIO_DIR = ROOT / "audio"

VOICE_FEMALE_STAFF = "en-US-AvaMultilingualNeural"
VOICE_CLIENT_MALE = "en-US-AndrewMultilingualNeural"
VOICE_CLIENT_FEMALE = "en-US-EmmaMultilingualNeural"
VOICE_MANAGER_FEMALE = "en-US-JennyNeural"

def extract_clips():
    html = HTML_PATH.read_text(encoding="utf-8")
    m_rescue = re.search(r"const RESCUE_PHRASES = (\[.*?\]);\n", html, re.S)
    m_courses = re.search(r"const COURSES = (\[.*?\]);\n", html, re.S)
    if not m_rescue or not m_courses:
        raise RuntimeError("Could not locate RESCUE_PHRASES or COURSES JSON in index.html")

    rescue = json.loads(m_rescue.group(1))
    courses = json.loads(m_courses.group(1))

    jobs = []
    for item in rescue:
        jobs.append((item["clipId"], item["en"], VOICE_FEMALE_STAFF))

    for cls in courses:
        for cw in cls["coreWords"]:
            text = f"{cw['word']}. {cw['ex']}"
            jobs.append((cw["clipId"], text, VOICE_FEMALE_STAFF))
        for scene in cls["scenarios"]:
            t_voice = VOICE_CLIENT_FEMALE if scene.get("teacherVoice") == "female" else VOICE_CLIENT_MALE
            if "Manager" in scene.get("teacherRole", "") and scene.get("teacherVoice") == "female":
                t_voice = VOICE_MANAGER_FEMALE
            for turn in scene["turns"]:
                voice = t_voice if turn["speaker"] == "T" else VOICE_FEMALE_STAFF
                jobs.append((turn["clipId"], turn["en"], voice))
    return jobs

async def synthesize_one(sem, clip_id, text, voice, retries=5):
    out_path = AUDIO_DIR / f"{clip_id}.mp3"
    if out_path.exists() and out_path.stat().st_size > 1000:
        return clip_id, "cached"

    fallback_voice = "en-US-AriaNeural" if "Ava" in voice or "Emma" in voice or "Jenny" in voice else "en-US-GuyNeural"
    async with sem:
        for attempt in range(retries):
            use_voice = voice if attempt < 3 else fallback_voice
            try:
                communicate = edge_tts.Communicate(text=text, voice=use_voice, rate="+0%")
                await communicate.save(str(out_path))
                if out_path.exists() and out_path.stat().st_size > 1000:
                    await asyncio.sleep(0.12)
                    return clip_id, "generated"
            except Exception as exc:
                if attempt == retries - 1:
                    raise RuntimeError(f"Failed {clip_id}: {exc}") from exc
                await asyncio.sleep(1.5 * (attempt + 1))
    return clip_id, "failed"

async def main():
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    jobs = extract_clips()
    print(f"Found {len(jobs)} total AI audio clips to verify/generate.")
    sem = asyncio.Semaphore(3)
    tasks = [synthesize_one(sem, cid, txt, v) for cid, txt, v in jobs]
    done = 0
    for coro in asyncio.as_completed(tasks):
        cid, status = await coro
        done += 1
        if done % 40 == 0 or done == len(jobs):
            print(f"[{done}/{len(jobs)}] latest={cid} ({status})")

if __name__ == "__main__":
    asyncio.run(main())
