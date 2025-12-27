import sys
import os
import json
import time
import re

from openai import OpenAI

def load_config():
    config_path = os.path.join(os.path.dirname(__file__), "config.json")
    with open(config_path, "r") as f:
        return json.load(f)

CONFIG = load_config()

LM_STUDIO_URL = CONFIG.get("lm_studio_url", "http://localhost:1234/v1")
MODEL_ID = CONFIG.get("lm_studio_model", "gpt-oss-20b")

def generate_prompt(steering_concept=None, image_base64=None, return_details=False):
    """
    Generates a prompt using the local LLM.
    If image_base64 is provided, uses vision model to describe/transform the image.
    Raises an exception if LM Studio connection fails.

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
            {"role": "system", "content": "You are a prompt engineer. Output ONLY the image generation prompt itself - no thinking, no reasoning, no preamble, no explanation. Start directly with the description."},
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
            {"role": "system", "content": "You are a prompt engineer. Output ONLY the image generation prompt itself - no thinking, no reasoning, no preamble, no explanation. Start directly with the description."},
            {"role": "user", "content": user_msg}
        ]
        print(f"[LLM] Requesting prompt from {MODEL_ID}...")

    try:
        response = client.chat.completions.create(
            model=MODEL_ID,
            messages=messages,
            temperature=0.7,
            max_tokens=1500
        )

        msg = response.choices[0].message
        prompt = msg.content.strip() if msg.content else ""

        if not prompt and hasattr(msg, 'reasoning_content') and msg.reasoning_content:
            prompt = msg.reasoning_content.strip()
        elif not prompt and 'reasoning' in msg.model_extra:
            prompt = msg.model_extra['reasoning'].strip()

        prompt = prompt.strip('"').strip("'")

        prompt = re.sub(r'^(Got it|Okay|Alright|Let me|I\'ll|I need to|Here\'s|Here is)[^.]*\.\s*', '', prompt, flags=re.IGNORECASE)
        prompt = re.sub(r'^(The user wants|This prompt)[^.]*\.\s*', '', prompt, flags=re.IGNORECASE)
        prompt = re.sub(r'<think>.*?</think>', '', prompt, flags=re.DOTALL)
        prompt = re.sub(r'<reasoning>.*?</reasoning>', '', prompt, flags=re.DOTALL)
        prompt = prompt.strip()

        if not prompt:
            raise RuntimeError("LLM returned empty prompt")

        result["prompt"] = prompt
        result["elapsed"] = round(time.time() - start_time, 2)
        print(f"[LLM] Generated prompt in {result['elapsed']}s: {prompt[:80]}...")
        return result if return_details else prompt

    except Exception as e:
        print(f"[Error] LLM generation failed: {e}")
        raise

if __name__ == "__main__":
    print(generate_prompt())