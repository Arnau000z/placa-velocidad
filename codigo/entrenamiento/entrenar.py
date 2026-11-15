"""Entrena un LoRA (SFT) sobre las respuestas del maestro, para la máquina con gráfica (CUDA).

El modelo aprende solo la respuesta final: el sistema, el historial y las fichas son el «prompt» y no cuentan en
la pérdida. Con una gráfica de 80-96 GB se entrena en bf16 sin cuantizar; con menos memoria, --4bit (QLoRA).

Uso (en la máquina alquilada):
    pip install -r entreno/requisitos.txt
    python entreno/entrenar.py --base Qwen/Qwen3-4B-Instruct-2507 --datos data/entreno/sft_corto.jsonl \
        --salida salidas/q3-4b-raft [--epocas 2] [--lr 1e-4] [--rango 16] [--4bit] [--prueba 20]
Con varias gráficas: torchrun --nproc_per_node 2 entreno/entrenar.py ... (y --acumular a la mitad, mismo lote efectivo).
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


def load(path: Path) -> list[dict]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    # Formato prompt/completion: TRL solo calcula la pérdida sobre la respuesta.
    return [{"prompt": r["messages"][:-1], "completion": r["messages"][-1:]} for r in rows]


def as_text(rows: list[dict], tokenizer) -> list[dict]:
    """Pasa prompt/completion de mensajes a texto con la plantilla del modelo, tal como lo recibe al usarlo.

    La plantilla de Gemma 4 pone un bloque de razonamiento vacío al abrir el turno del modelo solo cuando se le pide
    responder (add_generation_prompt), no al pintar la conversación entera: entrenando con mensajes, el modelo aprende
    a responder sin ese bloque y Ollama se lo pone siempre (31/10/2026). Con texto, el prompt es exactamente el de
    Ollama y la respuesta termina como en la conversación entera.
    """
    bos = tokenizer.bos_token or ""
    adds_bos = bool(bos) and tokenizer("x")["input_ids"][:1] == [tokenizer.bos_token_id]
    out = []
    # enable_thinking=False: lo mismo que pide el sistema a vLLM (COE_OPENAI_EXTRA), para que el prompt del entreno
    # sea byte a byte el que verá la Gemma al usarla (03/11/2026). Las plantillas que no lo usan lo ignoran.
    for row in rows:
        prompt = tokenizer.apply_chat_template(row["prompt"], tokenize=False, add_generation_prompt=True,
                                               enable_thinking=False)
        answer = row["completion"][0]["content"]
        full = tokenizer.apply_chat_template(row["prompt"] + row["completion"], tokenize=False, enable_thinking=False)
        end = full[full.rindex(answer) + len(answer):]
        if adds_bos and prompt.startswith(bos):  # el tokenizador ya lo añade: si no, irían dos
            prompt = prompt[len(bos):]
        out.append({"prompt": prompt, "completion": answer + end})
    return out


def _q4(weight):
    """Cuantiza por bloques de 32 como Q4_0 de llama.cpp: nibbles empaquetados (uint8) y una escala por bloque."""
    import torch

    shape = weight.shape
    blocks = weight.float().reshape(*shape[:-1], shape[-1] // 32, 32)
    peak = torch.gather(blocks, -1, blocks.abs().argmax(-1, keepdim=True))  # el de mayor |x|, con su signo
    scale = peak / -8
    inverse = torch.where(scale == 0, torch.zeros_like(scale), 1 / scale)
    q = (blocks * inverse + 8.5).floor().clamp(0, 15).to(torch.uint8).reshape(shape)
    return q[..., 0::2] | (q[..., 1::2] << 4), scale.squeeze(-1).half()


def _dq4(packed, scale, dtype):
    import torch

    q = torch.stack((packed & 15, packed >> 4), dim=-1).reshape(*packed.shape[:-1], packed.shape[-1] * 2)
    blocks = (q.to(dtype) - 8).reshape(*q.shape[:-1], q.shape[-1] // 32, 32) * scale.to(dtype).unsqueeze(-1)
    return blocks.reshape(q.shape)


def _experts_forward(self, hidden_states, top_k_index, top_k_weights):
    """Gemma4TextExperts.forward con los pesos en 4 bits: cada experto se descomprime solo cuando le toca."""
    import torch
    from torch import nn

    final = torch.zeros_like(hidden_states)
    with torch.no_grad():
        mask = nn.functional.one_hot(top_k_index, num_classes=self.num_experts + 1).permute(2, 1, 0)
        hit = torch.greater(mask.sum(dim=(-1, -2)), 0).nonzero()
    for expert in hit:
        expert = expert[0]
        if expert == self.num_experts:
            continue
        pos, token = torch.where(mask[expert])
        state = hidden_states[token]
        gate_up = _dq4(self.gate_up_q[expert], self.gate_up_s[expert], state.dtype)
        gate, up = nn.functional.linear(state, gate_up).chunk(2, dim=-1)
        out = nn.functional.linear(self.act_fn(gate) * up, _dq4(self.down_q[expert], self.down_s[expert], state.dtype))
        final.index_add_(0, token, (out * top_k_weights[token, pos, None]).to(final.dtype))
    return final


def compress_experts(model, device: str = "cuda") -> float:
    """Los expertos de la Gemma 26B (MoE) son tensores sueltos que QLoRA no cuantiza: en bf16 ocupan 46 GB y no caben
    en una gráfica de 48 GB. Se guardan en 4 bits (11,5 GB) y se descomprimen al usarlos; como los pesos QAT de Google
    están entrenados para Q4_0, se recuperan casi exactos. Se entrenan igual que con QLoRA: congelados, con el LoRA
    en la atención y las capas densas. Devuelve los GB que ocupan ahora."""
    import types

    import torch

    size = 0
    for module in model.modules():
        if type(module).__name__ != "Gemma4TextExperts":
            continue
        for name, short in (("gate_up_proj", "gate_up"), ("down_proj", "down")):
            weight = getattr(module, name).data.to(device)
            packed, scale = _q4(weight)
            delattr(module, name)
            module.register_buffer(f"{short}_q", packed)
            module.register_buffer(f"{short}_s", scale)
            size += packed.numel() + 2 * scale.numel()
            del weight
        module.forward = types.MethodType(_experts_forward, module)
    torch.cuda.empty_cache()
    return size / 1e9


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base", required=True, help="Modelo de Hugging Face, p. ej. Qwen/Qwen3-4B-Instruct-2507")
    parser.add_argument("--datos", type=Path, required=True)
    parser.add_argument("--salida", type=Path, required=True)
    parser.add_argument("--epocas", type=float, default=2)
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument("--rango", type=int, default=16)
    parser.add_argument("--lote", type=int, default=4, help="Ejemplos por paso en la gráfica")
    parser.add_argument("--acumular", type=int, default=4, help="Pasos que se acumulan (lote efectivo = lote x acumular)")
    parser.add_argument("--max-tokens", type=int, default=6144)
    parser.add_argument("--4bit", dest="cuatro_bits", action="store_true", help="QLoRA, para gráficas con poca memoria")
    parser.add_argument("--como-texto", dest="texto", action="store_true",
                        help="Entrenar con el texto de la plantilla, igual que al usarlo (necesario en Gemma 4, ver as_text)")
    parser.add_argument("--expertos-4bit", dest="expertos", action="store_true",
                        help="Gemma 26B (MoE) en 48 GB: expertos en 4 bits y el resto en bf16 (ver compress_experts)")
    parser.add_argument("--prueba", type=int, default=0, help="Solo N pasos, para comprobar que todo funciona")
    parser.add_argument("--cpu", action="store_true", help="Sin gráfica y en float32: solo para probar el guion en el PC")
    parser.add_argument("--completo", action="store_true", help="Ajustar todos los pesos (sin LoRA); usar lr bajo, 1e-5 a 3e-5")
    parser.add_argument("--unsloth", action="store_true",
                        help="Entrena con Unsloth: 1,4 veces más rápido y la misma pérdida (prueba_velocidad.py, 02/11/2026)")
    args = parser.parse_args()
    if args.unsloth and (args.expertos or args.cpu):
        raise SystemExit("--unsloth no está probado con --expertos-4bit ni con --cpu")

    if args.unsloth:
        from unsloth import FastLanguageModel  # antes que transformers: Unsloth los parchea al importarse
    import torch
    from datasets import Dataset
    from peft import LoraConfig
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    from trl import SFTConfig, SFTTrainer

    if args.unsloth:
        model, tokenizer = FastLanguageModel.from_pretrained(args.base, max_seq_length=args.max_tokens,
                                                             dtype=torch.bfloat16, load_in_4bit=args.cuatro_bits)
    else:
        tokenizer = AutoTokenizer.from_pretrained(args.base)
    quant = None
    if args.cuatro_bits and not args.unsloth:
        quant = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_use_double_quant=True,
                                   bnb_4bit_compute_dtype=torch.bfloat16)
    # Con varias gráficas (torchrun) cada proceso lleva el modelo entero en la suya y se reparten los ejemplos.
    rank = os.environ.get("LOCAL_RANK")
    device_map = "cpu" if args.cpu or args.expertos else ({"": int(rank)} if rank is not None else "auto")
    if not args.unsloth:
        model = AutoModelForCausalLM.from_pretrained(args.base, dtype=torch.float32 if args.cpu else torch.bfloat16,
                                                     quantization_config=quant, attn_implementation="sdpa",
                                                     device_map=device_map)
    if args.expertos:  # se carga en la CPU, se comprimen los expertos capa a capa en la gráfica y se sube el resto
        print(f"Expertos en 4 bits: {compress_experts(model):.1f} GB", flush=True)
        model.to("cuda")
        model.hf_device_map = {"": 0}
    val_path = args.datos.with_name(args.datos.stem + "_val.jsonl")
    train_rows = load(args.datos)
    val_rows = load(val_path) if val_path.exists() else None
    if args.texto:
        train_rows = as_text(train_rows, tokenizer)
        val_rows = as_text(val_rows, tokenizer) if val_rows else None
    train = Dataset.from_list(train_rows)
    val = Dataset.from_list(val_rows) if val_rows else None
    # En los modelos con visión (Gemma 4) el LoRA va solo al texto. Los expertos de la Gemma 26B (MoE) son tensores
    # sueltos, no capas Linear: no hay QLoRA que los cuantice (22,9 de los 25,8 mil millones de parámetros), así que
    # la Gemma se entrena en bf16 en una gráfica de 96 GB y el LoRA toca la atención y las capas densas.
    multimodal = any("language_model" in name for name, _ in model.named_modules())
    target = r".*language_model.*\.(q_proj|k_proj|v_proj|o_proj|gate_proj|up_proj|down_proj)" if multimodal else "all-linear"
    lora = LoraConfig(r=args.rango, lora_alpha=2 * args.rango, lora_dropout=0.05, task_type="CAUSAL_LM",
                      target_modules=target)
    if args.unsloth:
        if multimodal:  # 03/11/2026: se prueba con la Gemma 31B en una prueba corta; si falla, el guion usa el de siempre
            print("Aviso: --unsloth con un modelo con visión (Gemma 4) no está probado", flush=True)
        # El mismo LoRA (rango, alpha, dropout y capas) puesto por Unsloth, con su recálculo de activaciones.
        model = FastLanguageModel.get_peft_model(
            model, r=args.rango, lora_alpha=2 * args.rango, lora_dropout=0.05,
            target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
            use_gradient_checkpointing="unsloth", random_state=42)
        lora = None
    config = SFTConfig(
        output_dir=str(args.salida),
        num_train_epochs=args.epocas,
        max_steps=args.prueba or -1,
        learning_rate=args.lr,
        lr_scheduler_type="cosine",
        warmup_steps=10,  # transformers 5 ya no acepta warmup_ratio
        per_device_train_batch_size=args.lote,
        gradient_accumulation_steps=args.acumular,
        gradient_checkpointing=not args.unsloth,  # con Unsloth lo hace él
        gradient_checkpointing_kwargs={"use_reentrant": False},
        ddp_find_unused_parameters=False,
        bf16=not args.cpu,
        use_cpu=args.cpu,
        max_length=args.max_tokens,
        completion_only_loss=True,
        logging_steps=5,
        eval_strategy="epoch" if val is not None and not args.prueba else "no",
        per_device_eval_batch_size=args.lote,
        save_strategy="epoch" if not args.prueba else "no",
        save_total_limit=2,
        report_to="none",
        seed=int(os.environ.get("SEMILLA", "42")),
    )
    if args.completo:  # ajuste de todos los pesos: sin LoRA; el resultado se guarda ya "junto" para exportar.sh
        lora = None
    trainer = SFTTrainer(model=model, args=config, train_dataset=train, eval_dataset=val, processing_class=tokenizer,
                         peft_config=lora)
    trainer.train()
    destino = args.salida / ("junto" if args.completo else "lora")
    trainer.save_model(str(destino))
    tokenizer.save_pretrained(str(destino))
    history = [h for h in trainer.state.log_history if "loss" in h or "eval_loss" in h]
    (args.salida / "historial.json").write_text(json.dumps(history, indent=1), encoding="utf-8")
    print(f"LoRA guardado en {args.salida / 'lora'}")


if __name__ == "__main__":
    main()
