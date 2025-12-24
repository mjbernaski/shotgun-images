import random
import sys
import os
import json
import time

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

def load_config():
    config_path = os.path.join(os.path.dirname(__file__), "config.json")
    with open(config_path, "r") as f:
        return json.load(f)

CONFIG = load_config()

LM_STUDIO_URL = CONFIG.get("lm_studio_url", "http://localhost:1234/v1")
MODEL_ID = CONFIG.get("lm_studio_model", "gpt-oss-20b")

# --- Fallback Lists (Backup) ---
SUBJECTS = ["a majestic lion", "a futuristic cityscape", "a serene lake", "an astronaut", "a steampunk robot"]
STYLES = ["oil painting", "digital art", "photorealistic", "watercolor", "anime style"]
ARTISTS = ["Greg Rutkowski", "Alphonse Mucha", "H.R. Giger", "Vincent van Gogh", "Syd Mead"]
LIGHTING = ["cinematic lighting", "golden hour", "neon lights", "soft diffuse light"]
DETAILS = ["highly detailed", "4k resolution", "intricate textures", "sharp focus", "masterpiece"]

def generate_fallback_prompt(steering_concept=None):
    if steering_concept:
        subject = steering_concept
    else:
        subject = random.choice(SUBJECTS)
    
    style = random.choice(STYLES)
    artist = random.choice(ARTISTS)
    light = random.choice(LIGHTING)
    details = ", ".join(random.sample(DETAILS, 2))
    return f"{subject}, {style} by {artist}, {light}, {details}"

def generate_prompt(steering_concept=None, image_base64=None, return_details=False):
    """
    Generates a prompt using the local LLM.
    If image_base64 is provided, uses vision model to describe/transform the image.
    Falls back to list-based generation on error.

    If return_details=True, returns a dict with prompt, timing, and status info.
    """
    start_time = time.time()
    result = {
        "prompt": None,
        "elapsed": None,
        "model": MODEL_ID,
        "url": LM_STUDIO_URL,
        "mode": "vision" if image_base64 else "text",
        "source": "llm",
        "error": None
    }

    if not OpenAI:
        print("[Warning] 'openai' module not found. Using fallback generator.")
        prompt = generate_fallback_prompt(steering_concept)
        result["prompt"] = prompt
        result["source"] = "fallback"
        result["elapsed"] = round(time.time() - start_time, 2)
        return result if return_details else prompt

    client = OpenAI(base_url=LM_STUDIO_URL, api_key="lm-studio", timeout=300.0)

    if image_base64:
        if steering_concept:
            user_msg = (
                f"Look at this image and create a LONG, detailed image generation prompt (at least 80-120 words) to transform it "
                f"based on this concept: '{steering_concept}'. "
                "Describe the key elements you see, environment, mood, lighting, colors, textures, artistic style, and quality tags. "
                "Return ONLY the prompt string."
            )
        else:
            user_msg = (
                "Look at this image and create a LONG, detailed image generation prompt (at least 80-120 words) that describes it "
                "with artistic enhancements. Include subject details, environment, mood, lighting, colors, textures, artistic style, and quality tags. "
                "Return ONLY the prompt string."
            )

        if not image_base64.startswith("data:"):
            image_url = f"data:image/png;base64,{image_base64}"
        else:
            image_url = image_base64

        messages = [
            {"role": "system", "content": "You are a prompt engineer. Generate long, highly detailed prompts with rich descriptions of subject, environment, lighting, atmosphere, artistic style, and technical quality tags. Your output should be ONLY the final stable diffusion prompt string. No reasoning, no chatter."},
            {"role": "user", "content": [
                {"type": "text", "text": user_msg},
                {"type": "image_url", "image_url": {"url": image_url}}
            ]}
        ]
        print(f"[LLM] Requesting vision-based prompt from {MODEL_ID}...")
    else:
        if steering_concept:
            user_msg = (
                f"Create a LONG, detailed image prompt (at least 80-120 words) based on the concept: '{steering_concept}'. "
                "Include subject details, environment, mood, lighting, colors, textures, artistic style, and quality tags."
            )
        else:
            user_msg = (
                "Generate a LONG, detailed, creative image prompt (at least 80-120 words). "
                "Choose a unique subject and describe it with environment, mood, lighting, colors, textures, artistic style, and quality tags."
            )

        messages = [
            {"role": "system", "content": "You are a prompt engineer. Generate long, highly detailed prompts with rich descriptions of subject, environment, lighting, atmosphere, artistic style, and technical quality tags. Your output should be ONLY the final stable diffusion prompt string. No reasoning, no chatter."},
            {"role": "user", "content": user_msg}
        ]
        print(f"[LLM] Requesting prompt from {MODEL_ID}...")

    try:
        response = client.chat.completions.create(
            model=MODEL_ID,
            messages=messages,
            temperature=0.7,
            max_tokens=800
        )

        msg = response.choices[0].message
        prompt = msg.content.strip() if msg.content else ""

        if not prompt and hasattr(msg, 'reasoning_content') and msg.reasoning_content:
            prompt = msg.reasoning_content.strip()
        elif not prompt and 'reasoning' in msg.model_extra:
            prompt = msg.model_extra['reasoning'].strip()

        prompt = prompt.strip('"').strip("'")

        if not prompt:
            prompt = generate_fallback_prompt(steering_concept)
            result["source"] = "fallback"

        result["prompt"] = prompt
        result["elapsed"] = round(time.time() - start_time, 2)
        print(f"[LLM] Generated prompt in {result['elapsed']}s: {prompt[:80]}...")
        return result if return_details else prompt

    except Exception as e:
        print(f"[Error] LLM generation failed: {e}")
        print("[Info] Switching to fallback generator.")
        prompt = generate_fallback_prompt(steering_concept)
        result["prompt"] = prompt
        result["source"] = "fallback"
        result["error"] = str(e)
        result["elapsed"] = round(time.time() - start_time, 2)
        return result if return_details else prompt

if __name__ == "__main__":
    print(generate_prompt())