"""
3-way English interview: Neerja + Manish + Student.

Clean, simple implementation:
- AgentSession for Neerja (full: VAD built-in, STT, LLM, TTS)
- AgentSession for Manish (LLM + TTS only, audio disabled)
- Deterministic flow via on_user_turn_completed + StopResponse
- No custom mic control — framework handles everything
- Serves simple/index.html frontend at http://localhost:8080
"""

import asyncio, json, os, sys, threading, time
from datetime import timedelta

# Ensure prompts.py in same folder is found
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

os.environ.pop("SSL_CERT_FILE", None)

from aiohttp import web
from dotenv import load_dotenv
from livekit import agents, api
from livekit.agents import AgentServer, AgentSession, Agent, JobContext, RoomInputOptions, StopResponse
from livekit.plugins import openai as lk_openai, azure, silero
from openai import AzureOpenAI
import prompts

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"))

AGENT_NAME = "english-interview"
ROOM_NAME  = "english-practice"
server     = AgentServer()


# ── Caption helper ────────────────────────────────────────────────────────────
async def send_caption(room, role: str, text: str):
    await room.local_participant.publish_data(
        json.dumps({"role": role, "text": text}).encode(),
        reliable=True, topic="caption",
    )

async def speak(session: AgentSession, room, role: str, text: str):
    await send_caption(room, role, text)
    handle = session.say(text, allow_interruptions=False, add_to_chat_ctx=False)
    await handle.wait_for_playout()


# ── Manish — silent until called ─────────────────────────────────────────────
class Manish(Agent):
    def __init__(self):
        super().__init__(instructions=prompts.MANISH_SYSTEM)

    async def on_enter(self):
        pass  # never speak on entry


# ── Neerja — drives the interview ────────────────────────────────────────────
class Neerja(Agent):
    def __init__(self, manish_session: AgentSession, room):
        super().__init__(instructions=prompts.NEERJA_SYSTEM)
        self._manish_session = manish_session
        self._room   = room
        self._client = AzureOpenAI(
            api_key=os.getenv("AZURE_OPENAI_API_KEY"),
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
            api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
        )
        self._deploy = os.getenv("AZURE_OPENAI_DEPLOYMENT")
        self._phase  = "name"
        self._idx    = 0
        self._name   = "friend"
        self._busy   = False

    def _call_llm(self, system, user, max_tokens=80, json_mode=False, temperature=0.5):
        kw = {"response_format": {"type": "json_object"}} if json_mode else {}
        return self._client.chat.completions.create(
            model=self._deploy,
            messages=[{"role": "system", "content": system},
                      {"role": "user",   "content": user}],
            max_tokens=max_tokens, temperature=temperature, **kw,
        ).choices[0].message.content.strip()

    def _manish_answer(self, q):
        return self._call_llm(prompts.MANISH_SYSTEM, prompts.manish_answer_prompt(q), temperature=0.9)

    def _evaluate(self, q, answer, attempt=1):
        raw = self._call_llm(
            prompts.EVALUATOR_SYSTEM,
            prompts.evaluator_prompt(q, answer, attempt),
            max_tokens=100, json_mode=True,
        )
        try:
            d = json.loads(raw)
        except Exception:
            d = {}
        return {
            "rating":     d.get("rating", "NEEDS_IMPROVEMENT"),
            "correction": d.get("correction", answer),
            "reason":     d.get("reason", ""),
        }

    async def _neerja(self, text):
        await speak(self.session, self._room, "neerja", text)

    async def _manish_say(self, text):
        try:
            await speak(self._manish_session, self._room, "manish", text)
        except Exception as e:
            print(f"MANISH speak error: {e}", flush=True)

    async def _next(self, lead=""):
        self._idx += 1
        prefix = f"{lead} " if lead else ""
        if self._idx < len(prompts.QUESTIONS):
            self._phase = "question"
            await self._neerja(prefix + prompts.neerja_next(prompts.QUESTIONS[self._idx]))
        else:
            self._phase = "done"
            await self._neerja(prefix + prompts.NEERJA_CLOSING.format(name=self._name))
            await self._manish_say(prompts.MANISH_CLOSING.format(name=self._name))

    async def on_user_turn_completed(self, turn_ctx, new_message):
        if self._busy:
            raise StopResponse()

        answer = (new_message.text_content or "").strip()
        print(f"STUDENT >> {answer!r}  phase={self._phase}", flush=True)

        # Send student text via data channel FIRST so it appears above agent reply
        if answer:
            await send_caption(self._room, "student", answer)

        self._busy = True
        try:
            await self._handle(answer)
        except Exception as e:
            print(f"ERROR in _handle: {e}", flush=True)
            import traceback; traceback.print_exc()
        finally:
            self._busy = False
        raise StopResponse()

    async def _handle(self, answer):
        loop = asyncio.get_running_loop()

        # ── name ─────────────────────────────────────────────────────────────
        if self._phase == "name":
            if answer:
                self._name = answer.split()[-1].strip(".!,").capitalize()
            self._phase = "question"
            self._idx   = 0
            await self._neerja(prompts.neerja_welcome(self._name, prompts.QUESTIONS[0]))
            return

        # ── question (first attempt) ──────────────────────────────────────────
        if self._phase == "question":
            q = prompts.QUESTIONS[self._idx]
            if not answer:
                await self._neerja("I did not hear you. Please try to answer.")
                return

            # Neerja introduces Manish, Manish answers
            await self._neerja(prompts.neerja_bring_in_manish(self._name, q))
            manish_ans = await loop.run_in_executor(None, self._manish_answer, q)
            await self._manish_say(manish_ans)

            # Evaluate
            result = await loop.run_in_executor(None, self._evaluate, q, answer, 1)
            print(f"EVAL >> {result}", flush=True)

            if result["rating"] == "GOOD":
                await self._next()
            else:
                self._phase = "retry"
                await self._neerja(prompts.neerja_try_again(self._name, result.get("reason", "")))
            return

        # ── retry ────────────────────────────────────────────────────────────
        if self._phase == "retry":
            q = prompts.QUESTIONS[self._idx]
            result = await loop.run_in_executor(None, self._evaluate, q, answer, 2)
            print(f"RETRY EVAL >> {result}", flush=True)

            if answer and result["rating"] == "GOOD":
                await self._next(prompts.neerja_better(self._name))
            else:
                await self._next(prompts.neerja_correct_way(self._name, result["correction"]))
            return


# ── Room sessions ─────────────────────────────────────────────────────────────
@server.rtc_session(agent_name=AGENT_NAME)
async def entrypoint(ctx: JobContext):

    def llm():
        return lk_openai.LLM.with_azure(
            azure_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT"),
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
            api_key=os.getenv("AZURE_OPENAI_API_KEY"),
            api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
        )

    def tts(voice):
        return azure.TTS(
            speech_key=os.getenv("AZURE_SPEECH_KEY"),
            speech_region=os.getenv("AZURE_SPEECH_REGION"),
            voice=voice,
        )

    stt = azure.STT(
        speech_key=os.getenv("AZURE_SPEECH_KEY"),
        speech_region=os.getenv("AZURE_SPEECH_REGION"),
        language="en-IN",
        segmentation_silence_timeout_ms=1500,
    )

    # Manish — no audio input, only speaks when called
    manish_session = AgentSession(llm=llm(), tts=tts(os.getenv("MANISH_VOICE", "en-IN-PrabhatNeural")))
    await manish_session.start(
        room=ctx.room, agent=Manish(),
        room_input_options=RoomInputOptions(audio_enabled=False),
    )

    # Neerja — full session with explicitly downloaded Silero VAD
    neerja_session = AgentSession(
        vad=silero.VAD.load(),
        stt=stt, llm=llm(),
        tts=tts(os.getenv("AZURE_SPEECH_VOICE", "en-IN-NeerjaNeural")),
    )
    await neerja_session.start(room=ctx.room, agent=Neerja(manish_session, ctx.room))

    # Neerja greets immediately
    await speak(neerja_session, ctx.room, "neerja", prompts.NEERJA_INTRO)


# ── Web server (port 8080) ────────────────────────────────────────────────────
FRONTEND = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html")

async def handle_index(req):
    with open(FRONTEND, "r", encoding="utf-8") as f:
        return web.Response(text=f.read(), content_type="text/html")

async def handle_token(req):
    identity = f"student-{int(time.time())}"
    token = (
        api.AccessToken(
            api_key=os.getenv("LIVEKIT_API_KEY"),
            api_secret=os.getenv("LIVEKIT_API_SECRET"),
        )
        .with_identity(identity)
        .with_grants(api.VideoGrants(
            room_join=True, room=ROOM_NAME,
            can_publish=True, can_subscribe=True, can_publish_data=True,
        ))
        .with_ttl(timedelta(hours=1))
        .to_jwt()
    )
    try:
        async with api.LiveKitAPI() as lkapi:
            await lkapi.agent_dispatch.create_dispatch(
                api.CreateAgentDispatchRequest(agent_name=AGENT_NAME, room=ROOM_NAME)
            )
    except Exception as e:
        print(f"dispatch: {e}", flush=True)
    return web.json_response({"url": os.getenv("LIVEKIT_URL"), "token": token, "room": ROOM_NAME})

def run_web():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    app = web.Application()
    app.router.add_get("/", handle_index)
    app.router.add_get("/token", handle_token)
    web.run_app(app, port=8080, loop=loop, print=None)

if __name__ == "__main__":
    threading.Thread(target=run_web, daemon=True).start()
    agents.cli.run_app(server)
