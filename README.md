# Agent English Bot

A voice-based mock English job-interview practice app for Pratham Skilling Centre students.

Two AI characters guide the student through a short spoken interview:

- **Neerja** — the interview coach. Asks questions, listens to the student's spoken answer (via STT), evaluates it, and gives corrections or encouragement.
- **Manish** — a peer character who gives a sample spoken answer to each question, so the student has a model to compare against.

The student speaks into their microphone in the browser; audio flows over [LiveKit](https://livekit.io/) WebRTC to a Python agent process that runs STT → LLM (Azure OpenAI) → TTS (Azure Speech) for each turn.

## Project structure

```
Agent_english_bot/
├── app.py               # Entry point — python app.py <cmd>
├── src/
│   ├── main.py        # Agent logic, interview flow, LiveKit session wiring, web server
│   ├── prompts.py      # System prompts, question list, scripted phrase variants
│   ├── index.html      # Browser frontend (chat UI + mic controls)
│   └── image.png       # Reference/preview image
├── .env                 # Local secrets & config (not committed)
├── pyproject.toml       # Project deps (uv)
├── requirements.txt     # Project deps (pip)
└── uv.lock
```

## Requirements

- Python >= 3.11
- A LiveKit project (Cloud or self-hosted) — URL, API key, API secret
- Azure Speech resource (STT + TTS)
- Azure OpenAI resource with a chat-completions deployment

## Setup

1. Install dependencies:

   ```bash
   uv sync
   # or
   pip install -r requirements.txt
   ```

2. Copy `.env.example` to `.env` and fill in your own values:

   ```bash
   cp .env.example .env
   ```

## Running

Start the agent worker (LiveKit agents CLI, in dev mode with hot reload) via the `app.py` entry point:

```bash
uv run app.py dev
# or
python app.py dev
```

This also starts a small web server on **http://localhost:8080** serving `src/index.html`, which:

- fetches a LiveKit join token from `/token`
- connects to the room and enables the mic
- displays live captions for Neerja, Manish, and the student

Open http://localhost:8080 in a browser, allow microphone access, and start speaking.

## Interview flow

1. Neerja greets the student and asks their name.
2. For each question in `prompts.QUESTIONS`:
   - Neerja asks the question.
   - Manish gives a sample spoken answer.
   - The student answers; an LLM evaluator rates it `GOOD` / `NEEDS_IMPROVEMENT` / `POOR`.
   - If not `GOOD`, the student gets one retry with feedback before moving on.
3. Neerja and Manish close the interview with encouragement.
