import random

def pick(options):
    return random.choice(options)


NEERJA_SYSTEM = """
You are Neerja, a friendly English interview coach at Pratham Skilling Centre, India.
You are conducting a mock English job interview with a beginner student.
Keep all your language very simple and short. Be warm and patient.
""".strip()

MANISH_SYSTEM = """
You are Manish, 24 years old from Nashik, India.
Answer the interview question in ONE short simple sentence only.
Vary your wording naturally each time. Sound like a real person.
Do NOT greet or speak unless directly asked a question.
""".strip()

EVALUATOR_SYSTEM = """
You evaluate a student's spoken English answer in a mock job interview.
Return ONLY valid JSON:
{"rating": "GOOD" | "NEEDS_IMPROVEMENT" | "POOR", "correction": "...", "reason": "..."}

Judge the answer ON ITS OWN — any truthful answer is correct regardless of what anyone else said.
GOOD = answers the question and is understandable
NEEDS_IMPROVEMENT = tries to answer but English is broken or incomplete
POOR = does not answer or cannot be understood

"correction": grammatically correct version of THEIR answer (keep their own details).
"reason": max 8 simple words on what was wrong; empty string if GOOD.
""".strip()

def manish_answer_prompt(question):
    return f"Answer this interview question in one simple sentence: {question}"

def evaluator_prompt(question, answer, attempt=1):
    note = "Second attempt — be more lenient." if attempt == 2 else ""
    return f"Question: {question}\nStudent answered: {answer!r}\n{note}".strip()

# Scripted lines
NEERJA_INTRO = "Hello! I am Neerja. We also have Manish with us. What is your name?"

QUESTIONS = [
    "How old are you?",
    "Where do you live?",
    "What do you like to eat?",
    "Which colour do you like?",
    "What is your mother's name?",
]

def neerja_welcome(name, question):
    return pick([
        f"Nice to meet you, {name}! Let us begin. {question}",
        f"Welcome, {name}! First question. {question}",
        f"Great to meet you, {name}! Here is your first question. {question}",
    ])

def neerja_bring_in_manish(name, question):
    return pick([
        f"Okay {name}. Manish, {question}",
        f"Alright {name}. Manish, {question}",
        f"Hmm okay. Manish, {question}",
    ])

def neerja_next(question):
    return pick([
        f"Next question. {question}",
        f"Let us move on. {question}",
        f"Here is the next one. {question}",
    ])

def neerja_try_again(name, reason=""):
    r = (reason or "that was not quite right").rstrip(". ")
    return pick([
        f"Hmm {name}, {r}. Could you try again?",
        f"Almost, {name}! {r}. Please try once more.",
        f"Not quite, {name} — {r}. Can you say it again?",
    ])

def neerja_better(name):
    return pick([
        f"Much better, {name}!",
        f"Yes, {name}! That is right.",
        f"Perfect, {name}!",
    ])

def neerja_correct_way(name, correction):
    return pick([
        f"No problem, {name}. We say it like this: {correction}",
        f"Good effort, {name}. The correct way is: {correction}",
    ])

NEERJA_CLOSING = "Well done, {name}! You are getting ready for your interview. Goodbye!"
MANISH_CLOSING = "Goodbye, {name}! You will do great!"
