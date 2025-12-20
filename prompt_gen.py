import random
import sys
try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

# Local LM Studio Configuration
LM_STUDIO_URL = "http://localhost:1234/v1"
MODEL_ID = "gpt-oss-20b"

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

def generate_prompt(steering_concept=None):
    """
    Generates a prompt using the local LLM.
    Falls back to list-based generation on error.
    """
    if not OpenAI:
        print("[Warning] 'openai' module not found. Using fallback generator.")
        return generate_fallback_prompt(steering_concept)

    client = OpenAI(base_url=LM_STUDIO_URL, api_key="lm-studio")

    system_msg = (
        "You are an expert prompt engineer for Stable Diffusion/FLUX image generation. "
        "Your goal is to create highly visual, detailed, and creative image prompts. "
        "Return ONLY the prompt string. Do not add quotes or explanations."
    )

    if steering_concept:
        user_msg = (
            f"Create a detailed, high-quality image prompt based on the concept: '{steering_concept}'. "
            "Add artistic style, lighting, and details to make it a masterpiece."
        )
    else:
        user_msg = (
            "Generate a random, highly creative, and visually stunning image prompt. "
            "Choose a unique subject (fantasy, sci-fi, nature, etc.) and describe it vividly."
        )

    print(f"[LLM] Requesting prompt from {MODEL_ID}...")
    
    try:
        response = client.chat.completions.create(
            model=MODEL_ID,
            messages=[
                {"role": "system", "content": "You are a prompt engineer. Your output should be ONLY the final stable diffusion prompt string. No reasoning, no chatter."},
                {"role": "user", "content": user_msg}
            ],
            temperature=0.7,
            max_tokens=500
        )
        
        msg = response.choices[0].message
        prompt = msg.content.strip() if msg.content else ""
        
        # Handle reasoning models that might leave content empty but have reasoning_content
        if not prompt and hasattr(msg, 'reasoning_content') and msg.reasoning_content:
            prompt = msg.reasoning_content.strip()
        elif not prompt and 'reasoning' in msg.model_extra:
            # Some local servers put it in model_extra or model_fields
            prompt = msg.model_extra['reasoning'].strip()
            
        # Clean up if the LLM adds quotes despite instructions
        prompt = prompt.strip('"').strip("'")
        
        # If it's a reasoning block, it might be long. Let's hope it followed instructions.
        # If it's still empty, return fallback.
        if not prompt:
             return generate_fallback_prompt(steering_concept)
             
        return prompt

    except Exception as e:
        print(f"[Error] LLM generation failed: {e}")
        print("[Info] Switching to fallback generator.")
        return generate_fallback_prompt(steering_concept)

if __name__ == "__main__":
    print(generate_prompt())