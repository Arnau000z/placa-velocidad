"""Alquila la gráfica grande (96 GB) más barata de nube.offers() y la registra con la clave pedida: python alquilar_n.py 6"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import nube  # noqa: E402

clave = sys.argv[1]
d = nube.state()
if clave in d:
    raise SystemExit(f"la máquina {clave} ya existe: {d[clave]}")
offs = nube.offers()
print(len(offs), "ofertas;", [(o["id"], o["gpu_name"], round(o["dph_total"], 3), o.get("geolocation")) for o in offs[:4]])
pub = nube.KEY.with_suffix(".pub").read_text().strip()
onstart = "mkdir -p /root/.ssh && echo '%s' >> /root/.ssh/authorized_keys && chmod 600 /root/.ssh/authorized_keys" % pub
for o in offs[:4]:
    r = nube.vast("create", "instance", str(o["id"]), "--image", nube.IMAGE, "--disk", "150", "--ssh", "--direct", "--label", f"datathon-m{clave}",
                  "--cancel-unavail", "--onstart-cmd", onstart)
    print("respuesta para", o["id"], ":", str(r)[:200])
    if isinstance(r, dict) and r.get("new_contract"):
        d = nube.state()
        d[clave] = {"id": str(r["new_contract"]), "precio": o["dph_total"], "sitio": o.get("geolocation"), "gpu": o["gpu_name"]}
        nube.save(d)
        nube.vast("attach", "ssh", str(r["new_contract"]), pub)
        print(f"maquina {clave}:", r["new_contract"], o["gpu_name"], round(o["dph_total"], 3), "$/h")
        break
