import requests
import concurrent.futures
import webbrowser
import os
import json
import time

# Configuration
ENDPOINTS = [
    {"ip": "192.168.5.40", "port": 2222, "name": "Endpoint 1 (5.40)"},
    {"ip": "192.168.5.46", "port": 2222, "name": "Endpoint 2 (5.46)"}
]

# Default generation parameters
DEFAULT_CONFIG = {
    "orientation": "landscape",
    "size": "1mp",
    "steps": 25,
    "seed": None,
    "batch": 1
}

def generate_and_download(endpoint, prompt):
    """
    Sends a generation request to the endpoint and downloads the result.
    """
    base_url = f"http://{endpoint['ip']}:{endpoint['port']}"
    api_url = f"{base_url}/generate"
    
    payload = DEFAULT_CONFIG.copy()
    payload["prompt"] = prompt
    
    print(f"[{endpoint['name']}] Sending request...")
    
    try:
        start_time = time.time()
        response = requests.post(api_url, json=payload, timeout=300) # Long timeout for generation
        response.raise_for_status()
        data = response.json()
        
        if not data.get("success"):
            return {"error": f"API Error: {data.get('error')}", "endpoint": endpoint}

        # Assuming batch size 1 for simplicity, take the first image
        image_info = data["images"][0]
        image_filename = image_info["filename"]
        download_url = f"{base_url}/images/{image_filename}"
        
        # Download the image
        print(f"[{endpoint['name']}] Downloading image...")
        img_response = requests.get(download_url)
        img_response.raise_for_status()
        
        # Save locally
        local_filename = f"gen_{endpoint['ip'].replace('.', '_')}_{image_filename}"
        with open(local_filename, "wb") as f:
            f.write(img_response.content)
            
        return {
            "success": True,
            "local_path": local_filename,
            "endpoint": endpoint,
            "stats": image_info,
            "duration": time.time() - start_time
        }

    except Exception as e:
        return {"success": False, "error": str(e), "endpoint": endpoint}

def create_html_viewer(results, prompt):
    """
    Generates a simple HTML file to view results side-by-side.
    """
    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Dual Gen Results</title>
        <style>
            body {{ font-family: sans-serif; background: #222; color: #eee; padding: 20px; text-align: center; }}
            .container {{ display: flex; flex-wrap: wrap; gap: 20px; justify-content: center; margin-top: 20px; }}
            .card {{ background: #333; padding: 15px; border-radius: 8px; max-width: 45%; }}
            img {{ max-width: 100%; height: auto; border-radius: 4px; border: 1px solid #555; }}
            h2 {{ color: #00d4ff; margin-top: 0; }}
            .error {{ color: #ff6b6b; }}
            .meta {{ font-size: 0.9em; color: #aaa; margin-top: 10px; text-align: left; }}
        </style>
    </head>
    <body>
        <h1>Comparison for: "{prompt}"</h1>
        <div class="container">
    """

    for res in results:
        ep_name = res["endpoint"]["name"]
        if res.get("success"):
            stats = res["stats"]
            timings = stats.get("timings", {})
            html_content += f"""
            <div class="card">
                <h2>{ep_name}</h2>
                <img src="{res['local_path']}" alt="Result from {ep_name}">
                <div class="meta">
                    <p><strong>Seed:</strong> {stats.get('seed')}</p>
                    <p><strong>Total Time:</strong> {timings.get('total', 'N/A')}s</p>
                    <p><strong>Filename:</strong> {res['local_path']}</p>
                </div>
            </div>
            """
        else:
             html_content += f"""
            <div class="card">
                <h2>{ep_name}</h2>
                <p class="error">Failed: {res.get('error')}</p>
            </div>
            """

    html_content += """
        </div>
    </body>
    </html>
    """
    
    with open("viewer.html", "w") as f:
        f.write(html_content)
    return os.path.abspath("viewer.html")

import sys
import argparse
import prompt_gen

def main():
    print("--- Dual FLUX.2 Generator ---")
    
    parser = argparse.ArgumentParser(description="Generate images on two endpoints.")
    parser.add_argument("prompt", nargs="*", help="The prompt or steering concept")
    parser.add_argument("-r", "--random", action="store_true", help="Generate a random prompt (ad-lib). If a prompt is provided, it is used as the steering concept.")
    
    args = parser.parse_args()
    
    # Combine prompt parts if provided (e.g., "blue cat" becomes ["blue", "cat"] via nargs)
    user_input = " ".join(args.prompt).strip() if args.prompt else None
    
    if args.random:
        # Ad-lib mode
        prompt = prompt_gen.generate_prompt(steering_concept=user_input)
        print(f"Generated Prompt: {prompt}")
    elif user_input:
        # Literal mode
        prompt = user_input
    else:
        # Interactive mode fallback
        prompt = input("Enter your prompt: ").strip()
        
    if not prompt:
        print("Prompt cannot be empty.")
        return

    print(f"\nSending prompt to {len(ENDPOINTS)} endpoints concurrently...")
    
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future_to_endpoint = {
            executor.submit(generate_and_download, ep, prompt): ep 
            for ep in ENDPOINTS
        }
        
        results = []
        for future in concurrent.futures.as_completed(future_to_endpoint):
            results.append(future.result())
            
    # Sort results to match original order (optional, but looks better)
    results.sort(key=lambda x: x["endpoint"]["ip"])

    print("\nGeneration complete. Creating viewer...")
    viewer_path = create_html_viewer(results, prompt)
    
    print(f"Opening results in browser: {viewer_path}")
    webbrowser.open(f"file://{viewer_path}")

if __name__ == "__main__":
    main()
