import sys
import argparse
import prompt_gen
import csv
import time
import os
import json
import requests
import concurrent.futures
import webbrowser
from datetime import datetime

def load_config():
    config_path = os.path.join(os.path.dirname(__file__), "config.json")
    with open(config_path, "r") as f:
        return json.load(f)

CONFIG = load_config()

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

LOG_FILE = "generation_log.csv"

def log_result(result, prompt):
    """
    Appends generation details to a CSV log file.
    """
    file_exists = os.path.isfile(LOG_FILE)
    
    with open(LOG_FILE, "a", newline="", encoding="utf-8") as csvfile:
        fieldnames = ["timestamp", "endpoint", "prompt", "seed", "filename", "duration", "status", "error"]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        
        if not file_exists:
            writer.writeheader()
            
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        if result["success"]:
            writer.writerow({
                "timestamp": timestamp,
                "endpoint": result["endpoint"]["name"],
                "prompt": prompt,
                "seed": result["stats"].get("seed"),
                "filename": result["local_path"],
                "duration": f"{result['duration']:.2f}",
                "status": "Success",
                "error": ""
            })
        else:
            writer.writerow({
                "timestamp": timestamp,
                "endpoint": result["endpoint"]["name"],
                "prompt": prompt,
                "seed": "",
                "filename": "",
                "duration": "",
                "status": "Failed",
                "error": result.get("error", "Unknown error")
            })

def generate_and_download(endpoint, prompt, image_base64=None):
    """
    Sends a generation request to the endpoint and downloads the result.
    Optionally accepts a base64-encoded image for image-to-image generation.
    """
    base_url = f"http://{endpoint['ip']}:{endpoint['port']}"
    api_url = f"{base_url}/generate"

    payload = DEFAULT_CONFIG.copy()
    payload["prompt"] = prompt
    if image_base64:
        payload["image"] = image_base64
    
    print(f"[{endpoint['name']}] Sending request...")
    
    try:
        start_time = time.time()
        response = requests.post(api_url, json=payload, timeout=300) # Long timeout for generation
        response.raise_for_status()
        data = response.json()
        
        if not data.get("success"):
            return {"success": False, "error": f"API Error: {data.get('error')}", "endpoint": endpoint}

        # Assuming batch size 1 for simplicity, take the first image
        image_info = data["images"][0]
        image_filename = image_info["filename"]
        download_url = f"{base_url}/images/{image_filename}"
        
        # Download the image
        print(f"[{endpoint['name']}] Downloading image...")
        img_response = requests.get(download_url)
        img_response.raise_for_status()
        
        # Save to output directory
        output_dir = CONFIG.get("output_directory", ".")
        os.makedirs(output_dir, exist_ok=True)
        local_filename = f"gen_{endpoint['ip'].replace('.', '_')}_{image_filename}"
        local_path = os.path.join(output_dir, local_filename)
        with open(local_path, "wb") as f:
            f.write(img_response.content)
            
        return {
            "success": True,
            "local_path": local_path,
            "endpoint": endpoint,
            "stats": image_info,
            "duration": time.time() - start_time
        }

    except Exception as e:
        return {"success": False, "error": str(e), "endpoint": endpoint}

def create_html_viewer(all_results):
    """
    Generates a simple HTML file to view results side-by-side.
    all_results is a list of tuples: (prompt, [results_for_prompt])
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
            .session-block {{ border-bottom: 2px solid #444; padding-bottom: 40px; margin-bottom: 40px; }}
            .container {{ display: flex; flex-wrap: wrap; gap: 20px; justify-content: center; margin-top: 20px; }}
            .card {{ background: #333; padding: 15px; border-radius: 8px; max-width: 45%; }}
            img {{ max-width: 100%; height: auto; border-radius: 4px; border: 1px solid #555; }}
            h2 {{ color: #00d4ff; margin-top: 0; font-size: 1.2em; }}
            h1.prompt-title {{ color: #ffd700; font-size: 1.5em; margin-bottom: 10px; }}
            .error {{ color: #ff6b6b; }}
            .meta {{ font-size: 0.9em; color: #aaa; margin-top: 10px; text-align: left; }}
        </style>
    </head>
    <body>
        <h1>Dual Generator Session Results</h1>
    """

    for prompt, results in all_results:
        html_content += f"""
        <div class="session-block">
            <h1 class="prompt-title">Prompt: "{prompt}"</h1>
            <div class="container">
        """
        
        # Sort results by endpoint name for consistency
        results.sort(key=lambda x: x["endpoint"]["name"])

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
        html_content += "</div></div>"

    html_content += """
    </body>
    </html>
    """
    
    with open("viewer.html", "w") as f:
        f.write(html_content)
    return os.path.abspath("viewer.html")

def main():
    print("--- Dual FLUX.2 Generator ---")
    
    parser = argparse.ArgumentParser(description="Generate images on two endpoints.")
    parser.add_argument("prompt", nargs="*", help="The prompt or steering concept")
    parser.add_argument("-r", "--random", action="store_true", help="Generate a random prompt (ad-lib). If a prompt is provided, it is used as the steering concept.")
    parser.add_argument("-n", "--count", type=int, default=1, help="Number of times to repeat the generation (useful with -r).")
    
    args = parser.parse_args()
    
    # Combine prompt parts if provided
    user_input = " ".join(args.prompt).strip() if args.prompt else None
    
    session_results = [] # Stores (prompt, [results]) tuples

    for i in range(args.count):
        print(f"\n=== Run {i+1}/{args.count} ===")
        
        if args.random:
            # Ad-lib mode: Generate a new prompt each time
            current_prompt = prompt_gen.generate_prompt(steering_concept=user_input)
            print(f"Generated Prompt: {current_prompt}")
        elif user_input:
            # Literal mode: Reuse the same prompt (different seeds will naturally occur)
            current_prompt = user_input
        else:
            # Interactive mode fallback (only for the first run if count > 1, or repeated? Let's keep it simple)
            if i == 0:
                current_prompt = input("Enter your prompt: ").strip()
            # If user entered nothing in interactive mode, stop
            if not current_prompt:
                print("Prompt cannot be empty.")
                break
        
        print(f"Sending prompt to {len(ENDPOINTS)} endpoints concurrently...")
        
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future_to_endpoint = {
                executor.submit(generate_and_download, ep, current_prompt): ep 
                for ep in ENDPOINTS
            }
            
            run_results = []
            for future in concurrent.futures.as_completed(future_to_endpoint):
                res = future.result()
                run_results.append(res)
                log_result(res, current_prompt)
        
        session_results.append((current_prompt, run_results))

    if session_results:
        print("\nAll runs complete. Creating viewer...")
        viewer_path = create_html_viewer(session_results)
        print(f"Opening results in browser: {viewer_path}")
        webbrowser.open(f"file://{viewer_path}")
    else:
        print("No results to display.")

if __name__ == "__main__":
    main()
