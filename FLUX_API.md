# FLUX.2 API Reference

## Web Server API

The web server runs on port 2222 by default and provides both a web UI and REST API.

### Starting the Server

```bash
# Default (4-bit BNB model, remote encoder)
python web_server.py

# With GGUF model (recommended for DGX Spark)
python web_server.py --gguf q8

# Full model with local encoder
python web_server.py --full-model

# Custom port
python web_server.py --port 8080
```

**Server Options:**
| Option | Description |
|--------|-------------|
| `--local-encoder` | Use local text encoder instead of remote API (requires more VRAM) |
| `--full-model` | Use full FLUX.1-dev model instead of 4-bit quantized |
| `--gguf {bf16,q8,q4}` | Use GGUF model (recommended for DGX Spark unified memory) |
| `--port PORT` | Port to run server on (default: 2222) |

---

## REST API Endpoints

### POST /generate

Generate one or more images from a text prompt.

**Request Body (JSON):**

```json
{
  "prompt": "A majestic mountain landscape at sunset",
  "orientation": "landscape",
  "size": "1mp",
  "steps": 25,
  "seed": 12345,
  "batch": 1,
  "input_image": "data:image/png;base64,...",
  "strength": 0.75
}
```

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `prompt` | string | Yes | - | Text description of the image to generate |
| `orientation` | string | No | `landscape` | Image orientation: `square`, `portrait`, `landscape` |
| `size` | string | No | `1mp` | Resolution: `1mp`, `2mp`, `4mp` |
| `steps` | integer | No | 25 | Number of inference steps (10-50) |
| `seed` | integer | No | random | Random seed for reproducibility |
| `batch` | integer | No | 1 | Number of images to generate (1-4) |
| `input_image` | string | No | - | Base64-encoded reference image for guided generation |
| `strength` | float | No | 0.75 | Strength of reference image influence (0.0-1.0) |

**Orientation Dimensions (at 1MP):**

| Orientation | Width | Height |
|-------------|-------|--------|
| `square` | 1024 | 1024 |
| `portrait` | 768 | 1344 |
| `landscape` | 1344 | 768 |

**Size Multipliers:**

| Size | Multiplier | Example (landscape) |
|------|------------|---------------------|
| `1mp` | 1.0x | 1344 x 768 |
| `2mp` | 2.0x | 2688 x 1536 |
| `4mp` | 4.0x | 5376 x 3072 |

**Success Response (200):**

```json
{
  "success": true,
  "images": [
    {
      "filename": "flux2_20250104_143012_a1b2c3d4.png",
      "seed": 12345,
      "timings": {
        "encoding": 0.45,
        "diffusion": 12.34,
        "save": 0.12,
        "total": 12.91
      }
    }
  ],
  "generation_time": 13.05
}
```

**Error Response (400/500/503):**

```json
{
  "success": false,
  "error": "Error message describing what went wrong"
}
```

**Error Codes:**
- `400` - Bad request (missing prompt)
- `500` - Internal server error
- `503` - Generation already in progress

---

### GET /status

Check if an image generation is currently in progress.

**Response:**

```json
{
  "generating": true,
  "prompt": "A beautiful sunset",
  "batch": 2,
  "current": 1
}
```

| Field | Type | Description |
|-------|------|-------------|
| `generating` | boolean | Whether generation is in progress |
| `prompt` | string/null | Current prompt being generated |
| `batch` | integer | Total images in batch |
| `current` | integer | Current image being generated |

---

### GET /model-info

Get information about the loaded model configuration.

**Response:**

```json
{
  "model": "FLUX.1-dev-bnb-4bit",
  "encoder": "remote encoder",
  "description": "FLUX.1-dev-bnb-4bit with remote encoder"
}
```

**Possible Model Types:**
- `FLUX.1-dev-bnb-4bit` - 4-bit quantized model
- `FLUX.1-dev (full)` - Full precision model
- `FLUX.1-dev GGUF Q4` / `Q8` / `BF16` - GGUF quantized models

---

### GET /images/{filename}

Retrieve a generated image file.

**Response:** PNG image file

**Example:**
```
GET /images/flux2_20250104_143012_a1b2c3d4.png
```

---

### GET /

Serves the web UI for interactive image generation.

---

## CLI Usage

```bash
# Basic usage
python fl24bit.py

# With more inference steps
python fl24bit.py --steps 30

# With torch.compile for faster inference
python fl24bit.py --compile

# Use local text encoder
python fl24bit.py --local-encoder

# Use full model
python fl24bit.py --full-model

# Use GGUF model (recommended for DGX Spark)
python fl24bit.py --gguf q8
```

**CLI Options:**

| Option | Description |
|--------|-------------|
| `--steps N` | Number of inference steps (default: 25) |
| `--compile` | Compile model for faster inference (slower startup) |
| `--local-encoder` | Use local text encoder instead of remote API |
| `--full-model` | Use full FLUX.1-dev model |
| `--gguf {bf16,q8,q4}` | Use GGUF model |

**Interactive Commands:**

| Command | Description |
|---------|-------------|
| `quit` / `q` | Exit the program |
| `same` / `s` | Regenerate with same prompt (uses cached embeddings) |
| `reseed <number>` | Regenerate with specific seed |
| `/steps <number>` | Change inference steps |
| `/square` | Set square aspect ratio (1024x1024) |
| `/portrait` | Set portrait aspect ratio (768x1344) |
| `/landscape` | Set landscape aspect ratio (1344x768) |
| `/16:9` | Set 16:9 widescreen aspect ratio (1360x768) |
| `/1k` | Set 1K resolution |
| `/2k` | Set 2K resolution |
| `/4k` | Set 4K resolution |

**Inline Modifiers:** Commands can be embedded in prompts:
```
a beautiful sunset /4k /portrait
```

---

## Python API

### load_model()

Load the FLUX model components.

```python
from fl24bit import load_model

# Load 4-bit model with remote encoder (default)
load_model()

# Load with local encoder
load_model(local_encoder=True)

# Load full model
load_model(full_model=True)

# Load GGUF model
load_model(gguf_quant="q8")
```

### generate_image()

Generate an image from a text prompt.

```python
from fl24bit import generate_image

image, seed, timings = generate_image(
    prompt="A beautiful sunset over mountains",
    seed=12345,           # Optional, random if None
    steps=25,             # Inference steps
    width=1344,           # Output width
    height=768,           # Output height
    local_encoder=False,  # Use remote encoder
    input_image=None,     # Optional PIL Image for reference
    strength=0.75         # Reference image strength
)

# image: PIL.Image
# seed: int (the seed that was used)
# timings: dict with 'encoding', 'diffusion', 'total'
```

---

## Output Files

Generated images are saved with the naming pattern:
```
flux2_{YYYYMMDD}_{HHMMSS}_{uuid}.png
```

A corresponding `.prompt` file is saved with metadata:
```
# Raw input: a beautiful sunset /4k
# Prompt: a beautiful sunset
# Dimensions: 5376x3072
# Seed: 12345
# Steps: 25
# Timings: encoding=0.45s, diffusion=12.34s, save=0.12s
```

---

## Requirements

- CUDA-capable GPU
- Hugging Face token (via `huggingface-cli login` or `HF_TOKEN` environment variable)
- Python 3.10+
