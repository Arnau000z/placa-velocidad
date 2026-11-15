# Quan s'utilitzen els models d'IA a Math Coach

Anàlisi del codi de l'app `math-coach` (Arduino UNO Q, `~/ArduinoApps/math-coach/python/`) i de les dades de la placa, feta el 15/11/2026.

## Resum

| Model | Què és | On corre | Quan s'utilitza |
|---|---|---|---|
| **sopa_z10** (arquitectura Qwen3 1.7B, Q8_0) | Model de llenguatge | A la placa, `llama-server` al port 8081 (`math-llm.service`) | **Només** per generar la pista de l'**esglaó 3** quan l'alumne practica. |
| **bge-m3** (1024 dimensions) | Model d'embeddings | **Enlloc en temps d'execució.** Els vectors es van calcular abans, fora de la placa, i són dins de `data/bank.json`. | A tot arreu on l'app busca problemes "semblants": problema següent, esglaons 1 i 2, famílies de problemes i panell del docent. Només es multipliquen vectors desats. |
| **bge-small-en-v1.5** | Model d'embeddings | A la placa, `llama-server` al port 8082 (`math-embed.service`) | **Mai.** Està en marxa, però cap línia del codi de l'app el crida. |

En resum, l'app només fa crides a un model en un cas: quan un alumne demana la tercera pista d'un problema i aquesta pista no és a la memòria cau.

---

## 1. El model de llenguatge (sopa_z10)

### On encaixa: l'escala de pistes

A **Practicar**, l'alumne pot demanar ajuda fins a quatre vegades per problema. Cada ajuda resta punts. Un encert val `10 × (nivell + 1)`, i cada esglaó en treu una quarta part.

| Esglaó | Què veu l'alumne | Com es calcula |
|---|---|---|
| 1 | Un problema **resolt** semblant, d'un nivell inferior | Embeddings (bge-m3) |
| 2 | El **tema** i el **mètode** per resoldre'l | Embeddings + regles de paraules clau |
| **3** | **Una pista escrita pel model** | **LLM (sopa_z10)** |
| 4 | La solució | Dades del banc (sense model) |

### Els tres moments en què es pot cridar el model

1. **Precàrrega, quan l'alumne demana l'esglaó 1** (`api_hint`, `main.py:389`)
   Si la pista de l'esglaó 3 d'aquest problema i idioma no és a la memòria cau, s'encua amb **prioritat baixa** (`PREFETCH`). Així, quan l'alumne arriba a l'esglaó 3, sovint ja està feta.

2. **Quan l'alumne demana l'esglaó 3 i la pista no és a la memòria cau** (`main.py:398`)
   S'encua amb **prioritat alta** (`WAITED`) i passa al davant de les precàrregues. Mentre espera:
   - la matriu LED de la placa mostra el símbol "espera";
   - la pàgina consulta `/api/hint_status` periòdicament i mostra "pensant… N s" o quants alumnes té al davant a la cua.

3. **Quan la pista ja és a la memòria cau, no es crida el model.** Es mostra a l'instant, marcada amb ⚡.

### Com es fa la crida

- Hi ha **un sol fil treballador** (`hint_worker`) que atén les peticions **d'una en una** des d'una cua de prioritats. Si 20 alumnes demanen l'esglaó 3 alhora, s'esperen en fila.
- Petició: `POST /v1/chat/completions` (`coach.ask_hint`, `coach.py:429`):
  - instrucció de sistema en l'idioma de l'alumne (català, castellà o anglès): "dona UNA pista curta, de 25 paraules com a màxim, no donis mai la resposta…";
  - missatge: l'enunciat i les opcions, seguit de "Pista:";
  - `max_tokens: 60`, una gramàtica que obliga a respondre en una sola línia, i un temps màxim de 60 s.
- **Fins a dos intents** (`rung3_model_hint`): primer amb temperatura 0 (llavor 42) i, si la pista no passa els filtres, amb temperatura 0,8 (llavor 43).
- **Filtres** que s'apliquen a cada pista:
  - `leak_reason`: la rebutja si conté el valor de la resposta correcta o anomena la lletra correcta.
  - `useless_reason`: la rebutja si té menys de 6 paraules, o si menys d'un 25 % de les paraules són noves respecte de l'enunciat.
- **Si cap dels dos intents passa els filtres**, no es mostra cap pista del model. En el seu lloc es mostra el mètode del tema, com a l'esglaó 2.
- **Si el servidor no respon** o se supera el temps màxim, l'alumne veu un missatge d'error del model.

### Memòria cau

- Taula `hint_cache` de `profiles.db`, amb una entrada per **(problema, idioma)**. És permanent: es comparteix entre tots els alumnes i es manté després de reiniciar.
- Una entrada només es descarta si es va crear amb una versió anterior dels filtres (`HINT_VERSION = 2`).

### On NO s'utilitza el model de llenguatge

- **Tests** (tant els propis com els del docent): no tenen pistes.
- **Jocs en directe** (sales amb codi): no tenen pistes.
- **Lliçons pas a pas**: fan servir les solucions escrites del banc.
- **Panell del docent / "assistent d'IA"** (`insights.py`): **no fa servir cap LLM**. Combina un model d'habilitat (teoria de resposta a l'ítem, ajustat en línia com un Elo), les famílies d'embeddings, regles (alertes, errors compartits, grups) i un model de temps de resposta log-normal. Les frases que llegeix el docent les construeix la pàgina amb plantilles.

A `api_info`, `api_t_overview`, `api_t_model` i en arrencar l'app, el codi només **comprova** si el servidor és viu (`GET /health`) per mostrar-ne l'estat. No genera cap text.

---

## 2. Els embeddings (bge-m3, precalculats)

`data/bank.json` conté **810 problemes**, cadascun amb un vector de **1024 dimensions** del model **bge-m3**, calculat a partir del text en anglès. Les metadades indiquen que es van generar el 15/11/2026 a la 01:37. L'script que els va crear (`build_bank.py`) no és a la placa.

En arrencar, l'app calcula una sola vegada la matriu de similituds 810 × 810 (producte escalar dels vectors). Després només hi fa consultes. **No es calcula cap embedding nou mentre l'app funciona.**

| Moment / funció | Com s'utilitzen els embeddings |
|---|---|
| **Arrencada** | *k-means* esfèric → **24 famílies semàntiques** de problemes (`semantic_families`). Els noms de les famílies surten de paraules clau (TF-IDF), no de cap model. |
| **Practicar: problema següent** (`next_problem`) | Si l'alumne encerta, li toca el problema més semblant d'un nivell més amunt. Si falla, el més semblant del mateix tema, un nivell més avall. S'exclouen les còpies del mateix problema (similitud ≥ 0,88). |
| **Esglaó 1** (`rung1_easier_problem`) | El problema resolt més semblant d'un nivell inferior, sense còpies ni problemes amb el mateix valor de resposta. Els que tenen solució escrita reben un petit avantatge (+0,03). |
| **Esglaó 2** (`rung2_topic`) | El tema es decideix per votació entre el problema i els seus 5 veïns més semblants. |
| **Tests i jocs** (`pick_problems`) | Tria problemes alternant famílies perquè hi hagi varietat. Els tests del docent es poden limitar a una família. |
| **Revisió d'un test** | Mostra els punts febles de l'alumne per família. |
| **Lliçons** | Mostra les paraules clau de la família del problema. |
| **Panell del docent** | Mapa d'habilitats per família, grups d'alumnes amb la mateixa família feble, problemes recomanats per practicar (`practice_set`) i mesura de la coherència de les famílies. |
| **Medalles** | La medalla "explorador" s'aconsegueix encertant problemes de 5 famílies diferents. |

Sense `numpy`, l'app substitueix les famílies semàntiques pels temes de paraules clau.

---

## 3. El servidor d'embeddings bge-small (port 8082) no es fa servir

- `math-embed.service` està en marxa i ocupa memòria i CPU, però cap fitxer de l'app fa crides al port 8082.
- No hi pot ser compatible: els vectors de `bank.json` tenen **1024** dimensions (bge-m3) i bge-small en fa **384**.
- La capçalera de `coach.py` encara diu que el mapa és de "bge-small". El comentari està desactualitzat: el codi (`near_copy = 0.88` per a vectors de 1024) i les metadades del banc confirmen bge-m3.
- Si cap altra cosa de la placa no el necessita, es pot aturar per alliberar recursos per al model de llenguatge: `sudo systemctl stop math-embed`.

---

## 4. Dades reals de la placa

Dades preses de la memòria cau de pistes (`hint_cache`) el 15/11/2026:

| Mesura | Valor |
|---|---|
| Pistes desades | 25 (10 en català, 10 en castellà, 5 en anglès) |
| Crides al model | 30 (20 pistes en un intent, 5 en dos) |
| Temps per crida | mediana **20,5 s** (mínim 6,0 s, màxim 45,4 s) |
| Intents rebutjats per donar la resposta | 2 |
| Intents rebutjats per ser inútils | 4 |
| Problemes sense cap pista vàlida (es mostra el mètode) | 1 |
| Vegades que un alumne ha arribat a l'esglaó 3 | 0 (totes les pistes són precàrregues o proves) |

Amb uns **20 s per pista** i un sol fil treballador, la precàrrega a l'esglaó 1 és important. Sense ella, a classe es formaria cua de seguida.

### Observacions

- **23 de les 25 pistes desades són anteriors a l'arribada de `sopa_z10` a la placa** (08:02 UTC). Les va generar un model anterior. La memòria cau no guarda quin model va escriure cada pista, de manera que **en canviar de model les pistes antigues es continuen mostrant**. Els temps de la taula també inclouen aquestes generacions antigues. Per regenerar-les amb el model actual, cal buidar la taula `hint_cache` o pujar `HINT_VERSION` a `coach.py`.
- **El límit de 60 tokens pot tallar una pista a mitja frase.** Si la resposta no té cap punt final, `first_sentence` la retorna sencera. A la memòria cau n'hi ha una que acaba en "`… + 1 + 2 +`".
