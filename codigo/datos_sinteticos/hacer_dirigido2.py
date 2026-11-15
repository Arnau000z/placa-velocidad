"""Construye generar_dirigido2.py: generar_helmcode.py + las lecciones genéricas de los fallos de la sopa final
(experimentos/analisis/diagnosticos_z10.jsonl) + programas cortos (la sopa se queda sin tiempo en los largos)."""
import json

s = open(r"D:\Datathon_A\sintetico\generar_helmcode.py", encoding="utf-8").read()
D = [json.loads(l) for l in open(r"D:\Datathon_A\experimentos\analisis\diagnosticos_z10.jsonl", encoding="utf-8")]
lecciones = sorted({d["pista"].strip().rstrip(".") for d in D if d.get("generica") and d.get("pista")})
s = s.replace('"""Genera problemas sintéticos tipo Canguro',
              '"""(DIRIGIDO 2: lecciones de los fallos de la sopa final sopa_z10, experimentos/analisis/diagnosticos_z10.jsonl)\n'
              'Genera problemas sintéticos tipo Canguro', 1)
extra = ("\n\nThe student model that will learn from your programs makes these modelling mistakes (lessons from its real failures):\n"
         + "\n".join(f"- {l}" for l in lecciones)
         + "\nDesign every problem so that one of these traps decides the answer (a fast reader would pick a distractor), and make "
           "the program avoid the trap explicitly: encode EVERY condition of the statement (brute force over all cases with a check "
           "of each condition, exact Fractions, 'strictly'/'at least' exactly as written, unordered vs ordered as asked). "
           "Keep every program SHORT: at most 8 lines, no long lists typed by hand, always ending in print(...) of the computed "
           "value; the student runs out of time on long programs.")
marca = "Output ONLY a JSON array of {n} objects"
assert marca in s
s = s.replace(marca, extra.replace("{", "{{").replace("}", "}}") + "\n\n" + marca, 1)
viejo = "f\"gen_hc_{args.modelo.replace('.', '')}_{i:03d}.jsonl\""
assert viejo in s
s = s.replace(viejo, "f\"gen_dir2_{args.modelo.replace('.', '')}_{i:03d}.jsonl\"")
open(r"D:\Datathon_A\sintetico\generar_dirigido2.py", "w", encoding="utf-8", newline="\n").write(s)
print(len(lecciones), "lecciones")
