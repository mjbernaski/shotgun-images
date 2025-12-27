# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Dual Image Generator - A Flask web application that sends identical prompts to two FLUX image generation endpoints concurrently and displays results side-by-side. Includes LLM-powered prompt generation via LM Studio.

## Commands

```bash
# Run the web server (primary interface)
./run_web.sh
# or manually:
source venv/bin/activate && python web_server.py

# Run CLI tool directly
./run.sh "your prompt here"
./run.sh -r                    # random LLM-generated prompt
./run.sh -r "concept" -n 5     # 5 random prompts with steering concept
```

## Architecture

**Three-tier generation flow:**
1. `web_server.py` - Flask app with job queue, serves UI at configured port
2. `prompt_gen.py` - LLM client connecting to LM Studio for prompt generation (supports vision for img2img)
3. `dual_gen.py` - Handles concurrent requests to two FLUX endpoints, downloads/saves images

**Key patterns:**
- Jobs are processed sequentially via `queue.Queue` with a single background worker thread
- Both endpoints receive the same prompt (or optionally different prompts per endpoint)
- Images download to `output_directory` from config, served via `/images/<filename>`
- Generation results logged to `generation_log.csv`

**Endpoints are hardcoded** in `dual_gen.py:ENDPOINTS` - these are local network FLUX servers.

## Configuration

`config.json` contains:
- `output_directory`: Where generated images are saved
- `lm_studio_url`: LM Studio API endpoint for prompt generation
- `lm_studio_model`: Model ID for prompt generation
- `web_host`/`web_port`: Web server binding

## Frontend

Single-page app in `templates/index.html` with:
- Queue sidebar showing pending/running/completed jobs
- Real-time status polling for endpoint and LLM state
- Image upload for img2img generation
- Gallery view of all generated images
