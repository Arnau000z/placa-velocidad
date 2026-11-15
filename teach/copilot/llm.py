"""Ask the small language model for one letter, A to E.

Two settings in config.env (or environment variables) change how it asks:

ANSWER_MODE     how the model answers
  letter  one letter, A to E (the original baseline)
  value   the text of the correct option, e.g. "13"; Python maps it back to its letter.
          Falls back to letter when the options are pictures or two options are equal.
  calc    one short line of calculation, then "Answer: X"
EXAMPLE_ANSWER  how the solved RAG examples show their answer
  letter  "C"
  full    "C) 13" (the letter and the option's text)
"""
from .config import CONFIG
from .client import post

URL = f"http://127.0.0.1:{CONFIG['LLM_PORT']}/v1/chat/completions"
ANSWER_MODE = CONFIG.get("ANSWER_MODE", "letter")
EXAMPLE_ANSWER = CONFIG.get("EXAMPLE_ANSWER", "letter")
CALC_MAX_CHARS = int(CONFIG.get("CALC_MAX_CHARS", 160))

# Keep the system prompt stable: llama-server caches the start of the prompt,
# so text that never changes is only read once.
SYSTEM = ("You solve multiple-choice math competition problems for school students. "
          "Read the problem and the options, then reply with the letter of the correct option.")

ASK = {
    "letter": "\nAnswer:",
    "value": "\nReply with the correct option's value, exactly as written.\nAnswer:",
    "calc": "\nWrite one short line with the key calculation (numbers only, no introduction), "
            "then 'Answer: ' and the letter.",
}


def format_problem(problem, sees_image=False):
    lines = [problem["text"].strip()]
    options = problem.get("options") or {}
    for letter in "ABCDE":
        if letter in options:
            lines.append(f"{letter}) {options[letter]}")
    if not options:
        lines.append("(The options are in the picture.)" if sees_image else
                     "(The options are in a picture that you can't see. Pick the most likely letter.)")
    return "\n".join(lines)


def value_options(problem):
    """{value: letter} when all five options are text and distinct, else None."""
    options = problem.get("options") or {}
    values = {str(options.get(l, "")).strip(): l for l in "ABCDE"}
    if len(options) != 5 or "" in values or len(values) != 5:
        return None
    return values


def mode_for(problem, mode):
    return "letter" if mode == "value" and value_options(problem) is None else mode


def example_answer(ex, mode, example_answer_fmt):
    """The assistant turn for a solved example, in the same shape as the expected answer."""
    label = ex["label"]
    value = str((ex.get("options") or {}).get(label, "")).strip()
    full = f"{label}) {value}" if value else label
    if mode_for(ex, mode) == "value":
        return value
    shown = full if example_answer_fmt == "full" else label
    return f"Answer: {shown}" if mode == "calc" else shown


def build_messages(problem, examples=(), image_b64=None, mode=None, example_answer_fmt=None):
    """image_b64 is a PNG as base64 text. Only a server started with --mmproj can see it."""
    mode = mode or ANSWER_MODE
    example_answer_fmt = example_answer_fmt or EXAMPLE_ANSWER
    messages = [{"role": "system", "content": SYSTEM}]
    for ex in examples:  # solved problems retrieved with RAG, if any
        messages.append({"role": "user", "content": format_problem(ex) + ASK[mode_for(ex, mode)]})
        messages.append({"role": "assistant", "content": example_answer(ex, mode, example_answer_fmt)})
    text = format_problem(problem, sees_image=bool(image_b64)) + ASK[mode_for(problem, mode)]
    if image_b64:
        content = [{"type": "image_url", "image_url": {"url": "data:image/png;base64," + image_b64}},
                   {"type": "text", "text": text}]
    else:
        content = text
    messages.append({"role": "user", "content": content})
    return messages


def gbnf_literal(text):
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") \
        .replace("\r", "\\r").replace("\t", "\\t") + '"'


def grammar_and_tokens(problem, mode):
    """The grammar that forces the answer's shape, and how many tokens it may need."""
    if mode == "value":
        values = value_options(problem)
        return "root ::= " + " | ".join(gbnf_literal(v) for v in values), 64
    if mode == "calc":
        return (f'root ::= "Calculation: " calc "\\nAnswer: " [A-E]\ncalc ::= [^\\n]{{1,{CALC_MAX_CHARS}}}',
                CALC_MAX_CHARS // 2 + 10)
    return "root ::= [A-E]", 1


def answer_letter(problem, examples=(), timeout=60, image_b64=None, url=URL, mode=None,
                  example_answer_fmt=None):
    """Return (letter, timings, raw). The grammar makes any other output impossible."""
    mode = mode_for(problem, mode or ANSWER_MODE)
    grammar, max_tokens = grammar_and_tokens(problem, mode)
    response = post(url, {
        "messages": build_messages(problem, examples, image_b64, mode, example_answer_fmt),
        "grammar": grammar,
        "max_tokens": max_tokens,
        "temperature": 0,
        "seed": int(CONFIG["SEED"]),
        "cache_prompt": True,
    }, timeout=timeout)
    raw = response["choices"][0]["message"]["content"]
    if mode == "value":
        letter = value_options(problem).get(raw.strip(), CONFIG["FALLBACK_ANSWER"])
    elif mode == "calc":
        letter = raw.strip()[-1:] if raw.strip()[-1:] in "ABCDE" and raw.strip() else CONFIG["FALLBACK_ANSWER"]
    else:
        letter = raw.strip()
    return letter, response.get("timings", {}), raw
