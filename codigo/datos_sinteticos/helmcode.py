"""Cliente mínimo de Helmcode (API compatible con OpenAI, modelos abiertos del hackathon). Reintenta ante 429/5xx."""
import json
import time
import urllib.error
import urllib.request

KEY = open(r"D:\Datathon_A\.helmcode_key", encoding="utf-8").read().strip()
URL = "https://api.helmcode.com/v1/chat/completions"


def chat(model, messages, max_tokens=2000, temperature=0.0, reasoning_effort="none", timeout=600, intentos=6):
    payload = {"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature}
    if reasoning_effort:
        payload["reasoning_effort"] = reasoning_effort
    espera = 5
    for _ in range(intentos):
        try:
            req = urllib.request.Request(URL, json.dumps(payload).encode(), {"Content-Type": "application/json", "Authorization": f"Bearer {KEY}"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                d = json.load(r)
            m = d["choices"][0]["message"]
            return m.get("content") or "", d.get("usage", {})
        except urllib.error.HTTPError as e:
            ra = e.headers.get("Retry-After") if e.headers else None
            time.sleep(float(ra) if ra and ra.replace(".", "").isdigit() else espera)
            espera = min(60, espera * 2)
        except Exception:  # noqa: BLE001
            time.sleep(espera)
            espera = min(60, espera * 2)
    return "", {}
