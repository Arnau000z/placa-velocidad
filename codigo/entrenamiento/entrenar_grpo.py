"""GRPO (aprendizaje por refuerzo con recompensa verificable) para el 1.7B en el formato exacto de la placa.

Para cada problema el modelo genera N programas cortos; cada uno se ejecuta y la recompensa es:
  +1 si imprime el valor de la opción correcta, −0,3 si casa con otra opción, 0 si no casa,
  y una penalización suave por longitud (los programas largos no caben en 60 s en la placa).
Así se optimiza directamente "que el programa case con la opción correcta en pocos tokens".

python3 entrenar_grpo.py --base <modelo HF o carpeta junto> --problemas a.jsonl,b.jsonl --salida /root/salidas/17b_grpo
        [--pasos 150] [--generaciones 8] [--lr 1e-6] [--lora] [--prueba 2]
"""
import argparse
import concurrent.futures as cf
import json
import os
import random
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import torch
from datasets import Dataset
from transformers import AutoModelForCausalLM, AutoTokenizer
from trl import GRPOConfig, GRPOTrainer

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "experimentos"))
from util_opciones import LETTERS, extract_code, match_option  # noqa: E402

SYSTEM = """You solve Kangaroo math competition problems by writing a short Python 3 program.
Rules:
- Translate the statement into code faithfully: put the given numbers in variables, then compute. When the problem asks to count, to find a maximum/minimum, or which value satisfies conditions, try all the cases with loops instead of reasoning by hand.
- At most 8 short lines. No comments, no explanations, no functions unless really needed. Standard library only, no input(), must finish in under 2 seconds (never brute-force more than a million cases).
- The last line must be print(answer): the numeric value, or the exact text of the correct option (not its letter).
- Output only the code inside one ```python block."""
PRELUDIO = "from fractions import Fraction\nfrom math import *\nfrom itertools import *\nfrom collections import Counter\n"

p = argparse.ArgumentParser()
p.add_argument("--base", required=True)
p.add_argument("--problemas", required=True)
p.add_argument("--salida", type=Path, required=True)
p.add_argument("--pasos", type=int, default=150)
p.add_argument("--generaciones", type=int, default=8)
p.add_argument("--prompts-por-paso", type=int, default=8)
p.add_argument("--lr", type=float, default=1e-6)
p.add_argument("--max-tokens", type=int, default=220)
p.add_argument("--lora", action="store_true")
p.add_argument("--prueba", type=int, default=0)
p.add_argument("--max-problemas", type=int, default=4000)
args = p.parse_args()

tok = AutoTokenizer.from_pretrained(args.base)


def formato(r):
    return r["text"].strip() + "\n" + "\n".join(f"{k}) {r['options'][k]}" for k in LETTERS)


filas = []
for f in args.problemas.split(","):
    for l in open(f, encoding="utf-8"):
        if l.strip():
            r = json.loads(l)
            if len(r.get("options") or {}) == 5 and r.get("label") in LETTERS and r.get("text_only", True):
                filas.append(r)
random.Random(5).shuffle(filas)
filas = filas[:args.max_problemas]
datos = [{"prompt": tok.apply_chat_template([{"role": "system", "content": SYSTEM}, {"role": "user", "content": formato(r)}],
                                            tokenize=False, add_generation_prompt=True, enable_thinking=False),
          "opciones": json.dumps(r["options"], ensure_ascii=False), "label": r["label"]} for r in filas]
print(f"{len(datos)} problemas para GRPO", flush=True)


def ejecutar(code):
    code = re.sub(r"(?<=\d),(?=\d)", ".", code)
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as fh:
        fh.write(PRELUDIO + code)
        path = fh.name
    try:
        r = subprocess.run([sys.executable, "-I", "-S", path], capture_output=True, text=True, timeout=2, encoding="utf-8", errors="replace")
        return r.stdout
    except Exception:  # noqa: BLE001
        return ""
    finally:
        os.unlink(path)


def una(c, opciones, label):
    text = c if isinstance(c, str) else c[0]["content"]
    if "```" not in text:
        return -0.1
    code = extract_code(text)
    out = ejecutar(code)
    ultima = out.strip().splitlines()[-1].strip() if out.strip() else ""
    if not ultima or (len(ultima) == 1 and ultima.upper() in LETTERS):
        return 0.0
    letra, _ = match_option(out, json.loads(opciones))
    n = len(tok(text, add_special_tokens=False)["input_ids"])
    largo = -0.002 * max(0, n - 90)  # a partir de ~90 tokens empieza a no caber en la placa
    if letra == label:
        return 1.0 + largo
    if letra:
        return -0.3 + largo
    return largo


POOL = cf.ThreadPoolExecutor(16)


def recompensa(completions, opciones, label, **kwargs):
    return list(POOL.map(una, completions, opciones, label))


model = AutoModelForCausalLM.from_pretrained(args.base, dtype=torch.bfloat16, attn_implementation="sdpa")
peft_config = None
if args.lora:
    from peft import LoraConfig
    peft_config = LoraConfig(r=32, lora_alpha=64, lora_dropout=0.0, task_type="CAUSAL_LM", target_modules="all-linear")
config = GRPOConfig(
    output_dir=str(args.salida / "ckpt"),
    learning_rate=args.lr if not args.lora else max(args.lr, 1e-5),
    lr_scheduler_type="constant_with_warmup",
    warmup_steps=5,
    per_device_train_batch_size=args.prompts_por_paso * args.generaciones,
    gradient_accumulation_steps=1,
    num_generations=args.generaciones,
    max_completion_length=args.max_tokens,
    temperature=0.9,
    max_steps=args.prueba or args.pasos,
    beta=0.0,
    loss_type="dr_grpo",
    bf16=True,
    gradient_checkpointing=True,
    logging_steps=5,
    save_strategy="no",
    report_to="none",
    seed=42,
)
trainer = GRPOTrainer(model=model, reward_funcs=recompensa, args=config, train_dataset=Dataset.from_list(datos),
                      processing_class=tok, peft_config=peft_config)
trainer.train()
final = trainer.model
if args.lora:
    final = final.merge_and_unload()
(args.salida / "junto").mkdir(parents=True, exist_ok=True)
final.save_pretrained(str(args.salida / "junto"), safe_serialization=True)
tok.save_pretrained(str(args.salida / "junto"))
hist = [h for h in trainer.state.log_history if "reward" in h or "loss" in h]
(args.salida / "historial.json").write_text(json.dumps(hist, indent=1), encoding="utf-8")
print("GRPO terminado →", args.salida / "junto", flush=True)
