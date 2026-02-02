import os
import json
import time
import uuid
import base64
import threading
import queue
import requests
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_from_directory

ALLOWED_IMAGE_TYPES = {'jpeg', 'png', 'webp', 'gif'}
MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10MB

def detect_image_type(data):
    """Detect image type from file header bytes."""
    if len(data) < 12:
        return None
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return 'webp'
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        return 'png'
    if data[:2] == b'\xff\xd8':
        return 'jpeg'
    if data[:6] in (b'GIF87a', b'GIF89a'):
        return 'gif'
    return None

import prompt_gen
from dual_gen import generate_and_download, log_result, ENDPOINTS, CONFIG

endpoint_status = {ep["name"]: {"status": "unknown", "last_check": None} for ep in ENDPOINTS}

app = Flask(__name__, template_folder="templates", static_folder="static")

jobs = {}
job_queue = queue.Queue()
current_job_id = None

def load_config():
    config_path = os.path.join(os.path.dirname(__file__), "config.json")
    with open(config_path, "r") as f:
        return json.load(f)

def run_generation(job_id, prompt, use_random, steering_concept, count, image_base64=None, prompt_mode="same", prompt2=None, orientation="landscape", size="1mp", steps=25, seed=None, strength=0.75):
    """Background thread for running generation."""
    global current_job_id
    current_job_id = job_id
    jobs[job_id]["status"] = "running"
    jobs[job_id]["results"] = []
    jobs[job_id]["endpoint_status"] = {ep["name"]: {"state": "pending", "start_time": None, "elapsed": None} for ep in ENDPOINTS}
    jobs[job_id]["llm_status"] = {"state": "idle", "start_time": None, "elapsed": None, "model": None, "source": None}
    jobs[job_id]["started_at"] = time.time()

    for i in range(count):
        endpoint_prompts = {}

        if prompt_mode == "different":
            if use_random:
                jobs[job_id]["llm_status"] = {"state": "generating", "start_time": time.time(), "elapsed": None, "model": None, "source": None}
                for ep in ENDPOINTS:
                    llm_result = prompt_gen.generate_prompt(steering_concept=steering_concept, image_base64=image_base64, return_details=True)
                    endpoint_prompts[ep["name"]] = llm_result["prompt"]
                jobs[job_id]["llm_status"] = {
                    "state": "done" if llm_result["source"] == "llm" else "fallback",
                    "start_time": jobs[job_id]["llm_status"]["start_time"],
                    "elapsed": llm_result["elapsed"],
                    "model": llm_result["model"],
                    "source": llm_result["source"],
                    "mode": llm_result["mode"],
                    "error": llm_result.get("error")
                }
            else:
                endpoint_prompts[ENDPOINTS[0]["name"]] = prompt
                endpoint_prompts[ENDPOINTS[1]["name"]] = prompt2 or prompt
        else:
            if use_random:
                jobs[job_id]["llm_status"] = {"state": "generating", "start_time": time.time(), "elapsed": None, "model": None, "source": None}
                llm_result = prompt_gen.generate_prompt(steering_concept=steering_concept, image_base64=image_base64, return_details=True)
                current_prompt = llm_result["prompt"]
                jobs[job_id]["llm_status"] = {
                    "state": "done" if llm_result["source"] == "llm" else "fallback",
                    "start_time": jobs[job_id]["llm_status"]["start_time"],
                    "elapsed": llm_result["elapsed"],
                    "model": llm_result["model"],
                    "source": llm_result["source"],
                    "mode": llm_result["mode"],
                    "error": llm_result.get("error")
                }
            else:
                current_prompt = prompt
            for ep in ENDPOINTS:
                endpoint_prompts[ep["name"]] = current_prompt

        jobs[job_id]["current_run"] = i + 1
        jobs[job_id]["current_prompt"] = endpoint_prompts.get(ENDPOINTS[0]["name"], "")
        jobs[job_id]["endpoint_prompts"] = endpoint_prompts
        start_time = time.time()
        for ep in ENDPOINTS:
            jobs[job_id]["endpoint_status"][ep["name"]] = {"state": "generating", "start_time": start_time, "elapsed": None}

        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future_to_endpoint = {
                executor.submit(generate_and_download, ep, endpoint_prompts[ep["name"]], image_base64, orientation, size, steps, seed, strength): ep
                for ep in ENDPOINTS
            }

            run_results = []
            for future in concurrent.futures.as_completed(future_to_endpoint):
                ep = future_to_endpoint[future]
                res = future.result()
                res["prompt_used"] = endpoint_prompts[ep["name"]]
                run_results.append(res)
                log_result(res, endpoint_prompts[ep["name"]])
                elapsed = time.time() - start_time
                jobs[job_id]["endpoint_status"][ep["name"]] = {
                    "state": "done" if res.get("success") else "error",
                    "start_time": start_time,
                    "elapsed": round(elapsed, 1)
                }

        jobs[job_id]["results"].append({
            "prompt": endpoint_prompts.get(ENDPOINTS[0]["name"], ""),
            "endpoint_prompts": endpoint_prompts,
            "images": run_results
        })

    jobs[job_id]["status"] = "complete"
    jobs[job_id]["completed_at"] = datetime.now().isoformat()
    jobs[job_id]["total_elapsed"] = round(time.time() - jobs[job_id]["started_at"], 1)
    current_job_id = None


def queue_worker():
    """Background worker that processes jobs from the queue sequentially."""
    while True:
        job_data = job_queue.get()
        if job_data is None:
            break
        job_id = job_data.get("job_id")
        if job_id and job_id in jobs and jobs[job_id]["status"] == "cancelled":
            job_queue.task_done()
            continue
        try:
            run_generation(**job_data)
        except Exception as e:
            if job_id and job_id in jobs:
                jobs[job_id]["status"] = "error"
                jobs[job_id]["error"] = str(e)
        job_queue.task_done()


worker_thread = None

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/gallery")
def gallery():
    return render_template("gallery.html")

@app.route("/api/generate", methods=["POST"])
def api_generate():
    image_base64 = None
    print(f"[WebServer] Content-Type: {request.content_type}")
    print(f"[WebServer] Files: {list(request.files.keys())}")

    if request.content_type and request.content_type.startswith("multipart/form-data"):
        prompt = request.form.get("prompt", "").strip()
        prompt2 = request.form.get("prompt2", "").strip()
        use_random = request.form.get("random", "").lower() in ("true", "1", "yes")
        count = int(request.form.get("count", 1))
        prompt_mode = request.form.get("prompt_mode", "same")
        orientation = request.form.get("orientation", "landscape")
        size = request.form.get("size", "1mp")
        steps = int(request.form.get("steps", 25))
        seed_str = request.form.get("seed", "")
        seed = int(seed_str) if seed_str else None
        strength = float(request.form.get("strength", 0.75))
        if "image" in request.files:
            image_file = request.files["image"]
            if image_file.filename:
                image_data = image_file.read()

                if len(image_data) > MAX_IMAGE_SIZE:
                    return jsonify({"error": f"Image too large. Maximum size is {MAX_IMAGE_SIZE // (1024*1024)}MB"}), 400

                image_type = detect_image_type(image_data)
                if image_type not in ALLOWED_IMAGE_TYPES:
                    return jsonify({"error": f"Invalid image format: {image_type or 'unknown'}. Supported: JPEG, PNG, WebP, GIF"}), 400

                image_base64 = base64.b64encode(image_data).decode("utf-8")
                print(f"[WebServer] Received image: {image_file.filename} ({len(image_data)} bytes, {len(image_base64)} base64 chars)")
    else:
        data = request.json or {}
        prompt = data.get("prompt", "").strip()
        prompt2 = data.get("prompt2", "").strip()
        use_random = data.get("random", False)
        count = int(data.get("count", 1))
        prompt_mode = data.get("prompt_mode", "same")
        orientation = data.get("orientation", "landscape")
        size = data.get("size", "1mp")
        steps = int(data.get("steps", 25))
        seed = data.get("seed")
        strength = float(data.get("strength", 0.75))
        image_base64 = data.get("image")

    if not use_random and not prompt:
        return jsonify({"error": "Prompt is required when not using random mode"}), 400

    if prompt_mode == "different" and not use_random and not prompt2:
        prompt2 = prompt

    job_id = str(uuid.uuid4())[:8]
    queue_position = job_queue.qsize() + (1 if current_job_id else 0)
    jobs[job_id] = {
        "id": job_id,
        "status": "queued",
        "prompt": prompt,
        "prompt2": prompt2,
        "prompt_mode": prompt_mode,
        "random": use_random,
        "count": count,
        "has_image": image_base64 is not None,
        "current_run": 0,
        "current_prompt": "",
        "queue_position": queue_position,
        "results": [],
        "created_at": datetime.now().isoformat()
    }

    job_queue.put({
        "job_id": job_id,
        "prompt": prompt,
        "use_random": use_random,
        "steering_concept": prompt if use_random else None,
        "count": count,
        "image_base64": image_base64,
        "prompt_mode": prompt_mode,
        "prompt2": prompt2,
        "orientation": orientation,
        "size": size,
        "steps": steps,
        "seed": seed,
        "strength": strength
    })

    return jsonify({"job_id": job_id, "status": "queued", "queue_position": queue_position})

@app.route("/api/status/<job_id>")
def api_status(job_id):
    if job_id not in jobs:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(jobs[job_id])

@app.route("/api/jobs")
def api_jobs():
    return jsonify(list(jobs.values()))

@app.route("/api/queue")
def api_queue():
    """Return queue state with pending, running, and completed jobs."""
    pending = []
    running = []
    completed = []

    sorted_jobs = sorted(jobs.values(), key=lambda x: x.get("created_at", ""), reverse=True)

    for job in sorted_jobs:
        if job["status"] == "queued":
            pending.append(job)
        elif job["status"] == "running":
            running.append(job)
        elif job["status"] in ("complete", "error"):
            completed.append(job)

    return jsonify({
        "pending": pending,
        "running": running,
        "completed": completed[:20],
        "current_job_id": current_job_id,
        "queue_size": job_queue.qsize()
    })

@app.route("/api/queue/<job_id>", methods=["DELETE"])
def api_cancel_job(job_id):
    """Cancel a pending job."""
    if job_id not in jobs:
        return jsonify({"error": "Job not found"}), 404

    job = jobs[job_id]
    if job["status"] != "queued":
        return jsonify({"error": "Can only cancel queued jobs"}), 400

    job["status"] = "cancelled"
    return jsonify({"success": True, "job_id": job_id})

@app.route("/api/queue/clear", methods=["POST"])
def api_clear_queue():
    """Clear all pending and completed jobs from the queue."""
    global jobs

    # Clear the queue
    while not job_queue.empty():
        try:
            job_queue.get_nowait()
            job_queue.task_done()
        except:
            break

    # Remove all jobs except the currently running one
    if current_job_id:
        current = jobs.get(current_job_id)
        jobs = {current_job_id: current} if current else {}
    else:
        jobs = {}

    return jsonify({"success": True})

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
    for f in os.listdir(output_dir):
        if f.startswith("._"):
            continue
        if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
            filepath = os.path.join(output_dir, f)
            stat = os.stat(filepath)
            images.append({
                "filename": f,
                "url": f"/images/{f}",
                "created": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "mtime": stat.st_mtime,
                "size": stat.st_size
            })
    images.sort(key=lambda x: x["mtime"], reverse=True)
    limit = min(int(request.args.get("limit", 100)), 1000)
    return jsonify(images[:limit])

if __name__ == "__main__":
    config = load_config()
    host = config.get("web_host", "0.0.0.0")
    port = config.get("web_port", 5000)

    worker_thread = threading.Thread(target=queue_worker, daemon=True)
    worker_thread.start()

    print(f"Starting Dual Image Generator Web UI")
    print(f"Local: http://127.0.0.1:{port}")
    print(f"Network: http://0.0.0.0:{port} (access from other devices on your network)")

    app.run(host=host, port=port, debug=True)
