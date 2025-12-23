import os
import json
import time
import uuid
import base64
import threading
import requests
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_from_directory

import prompt_gen
from dual_gen import generate_and_download, log_result, ENDPOINTS, CONFIG

endpoint_status = {ep["name"]: {"status": "unknown", "last_check": None} for ep in ENDPOINTS}

app = Flask(__name__, template_folder="templates", static_folder="static")

jobs = {}

def load_config():
    config_path = os.path.join(os.path.dirname(__file__), "config.json")
    with open(config_path, "r") as f:
        return json.load(f)

def run_generation(job_id, prompt, use_random, steering_concept, count, image_base64=None):
    """Background thread for running generation."""
    jobs[job_id]["status"] = "running"
    jobs[job_id]["results"] = []
    jobs[job_id]["endpoint_status"] = {ep["name"]: "pending" for ep in ENDPOINTS}

    for i in range(count):
        if use_random:
            current_prompt = prompt_gen.generate_prompt(steering_concept=steering_concept)
        else:
            current_prompt = prompt

        jobs[job_id]["current_run"] = i + 1
        jobs[job_id]["current_prompt"] = current_prompt
        for ep in ENDPOINTS:
            jobs[job_id]["endpoint_status"][ep["name"]] = "generating"

        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future_to_endpoint = {
                executor.submit(generate_and_download, ep, current_prompt, image_base64): ep
                for ep in ENDPOINTS
            }

            run_results = []
            for future in concurrent.futures.as_completed(future_to_endpoint):
                ep = future_to_endpoint[future]
                res = future.result()
                run_results.append(res)
                log_result(res, current_prompt)
                jobs[job_id]["endpoint_status"][ep["name"]] = "done" if res.get("success") else "error"

        jobs[job_id]["results"].append({
            "prompt": current_prompt,
            "images": run_results
        })

    jobs[job_id]["status"] = "complete"
    jobs[job_id]["completed_at"] = datetime.now().isoformat()

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/generate", methods=["POST"])
def api_generate():
    image_base64 = None
    print(f"[WebServer] Content-Type: {request.content_type}")
    print(f"[WebServer] Files: {list(request.files.keys())}")

    if request.content_type and request.content_type.startswith("multipart/form-data"):
        prompt = request.form.get("prompt", "").strip()
        use_random = request.form.get("random", "").lower() in ("true", "1", "yes")
        count = int(request.form.get("count", 1))
        if "image" in request.files:
            image_file = request.files["image"]
            if image_file.filename:
                image_data = image_file.read()
                image_base64 = base64.b64encode(image_data).decode("utf-8")
                print(f"[WebServer] Received image: {image_file.filename} ({len(image_data)} bytes, {len(image_base64)} base64 chars)")
    else:
        data = request.json or {}
        prompt = data.get("prompt", "").strip()
        use_random = data.get("random", False)
        count = int(data.get("count", 1))
        image_base64 = data.get("image")

    if not use_random and not prompt:
        return jsonify({"error": "Prompt is required when not using random mode"}), 400

    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = {
        "id": job_id,
        "status": "queued",
        "prompt": prompt,
        "random": use_random,
        "count": count,
        "has_image": image_base64 is not None,
        "current_run": 0,
        "current_prompt": "",
        "results": [],
        "created_at": datetime.now().isoformat()
    }

    thread = threading.Thread(
        target=run_generation,
        args=(job_id, prompt, use_random, prompt if use_random else None, count, image_base64)
    )
    thread.start()

    return jsonify({"job_id": job_id, "status": "queued"})

@app.route("/api/status/<job_id>")
def api_status(job_id):
    if job_id not in jobs:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(jobs[job_id])

@app.route("/api/jobs")
def api_jobs():
    return jsonify(list(jobs.values()))

@app.route("/images/<path:filename>")
def serve_image(filename):
    output_dir = CONFIG.get("output_directory", ".")
    return send_from_directory(output_dir, filename)

@app.route("/api/endpoints")
def api_endpoints():
    """Check health of all endpoints."""
    results = []
    for ep in ENDPOINTS:
        status = {"name": ep["name"], "ip": ep["ip"], "port": ep["port"]}
        try:
            url = f"http://{ep['ip']}:{ep['port']}/"
            resp = requests.get(url, timeout=3)
            status["status"] = "online"
        except requests.exceptions.Timeout:
            status["status"] = "timeout"
        except requests.exceptions.ConnectionError:
            status["status"] = "offline"
        except Exception as e:
            status["status"] = "online"
        results.append(status)
    return jsonify(results)

@app.route("/api/gallery")
def api_gallery():
    """List all generated images."""
    output_dir = CONFIG.get("output_directory", ".")
    if not os.path.exists(output_dir):
        return jsonify([])

    images = []
    for f in sorted(os.listdir(output_dir), reverse=True):
        if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
            stat = os.stat(os.path.join(output_dir, f))
            images.append({
                "filename": f,
                "url": f"/images/{f}",
                "created": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "size": stat.st_size
            })
    return jsonify(images[:100])

if __name__ == "__main__":
    config = load_config()
    host = config.get("web_host", "0.0.0.0")
    port = config.get("web_port", 5000)

    print(f"Starting Dual Image Generator Web UI")
    print(f"Local: http://127.0.0.1:{port}")
    print(f"Network: http://0.0.0.0:{port} (access from other devices on your network)")

    app.run(host=host, port=port, debug=True)
