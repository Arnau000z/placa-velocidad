# Math Coach: a classroom maths platform with an AI teaching assistant, on the Arduino UNO Q

The board serves a web app to the whole class over its Wi-Fi. Students pick their name in their
class and type a 4-digit PIN. Then they **practise** (adaptive trainer + hint ladder), take
**tests** (their own or the teacher's), play **live games** with friends in a room (same problem
for everyone, points for right and fast answers), and **learn step by step** from solved
problems. The **teacher** sees the class through an AI assistant that runs on the board: each
student's real level, alerts, shared misconceptions, support groups, response times and pace
profiles. Kangaroo problems (M3Kang), Catalan, Spanish and English, offline (no cloud, no CDN: the font
and the icons are bundled with the app). The LED matrix shows a tick or a cross and the level of the last answer.

## For students

| Section | What it does |
| --- | --- |
| Login | Class tabs, a card per student with their avatar (online dot), a PIN pad with big keys (and the keyboard). PINs are PBKDF2 hashes; 5 wrong tries lock that student for 60 s |
| Home | Level estimated by the AI with a progress bar to the next level, points, accuracy, streak, wins; four activities; the teacher's open tests; open game rooms in the class; badges; class ranking with podium |
| Practise | The adaptive trainer and the 4-rung hint ladder (below). Points 10 x (level + 1), -25% per hint. A session bar of 10 problems on top; pick an answer, then **Check**; a bottom bar gives the verdict (points, streak, level up) and one **Continue** button, while the card shows the worked solution, the time taken and a link to learn that problem step by step |
| Tests | Level (the AI recommends one) and 5/10/15 questions, or a test set by the teacher (optional time limit). No hints; pick then confirm. Result: score ring, points, median time per question, families to review, every question with its explanation |
| Play with friends | Create a room (rounds, seconds per question, level or automatic = the group's average level), share the 4-letter code. Everyone gets the same problem; each answer has its own colour **and** shape (triangle, diamond, circle, square, star); 100 points + up to 100 for speed. Live: who has answered, countdown, reveal with who chose each option, scoreboard, podium and confetti at the end. The host can skip the wait between rounds |
| Learn step by step | 396 solved problems, filterable by level and topic. A slow lesson: read calmly; what are we asked (the question sentence); what do we know (the numbers); which idea helps (topic and method); guess first (doesn't count); the solution one step at a time; the answer. Read aloud with the browser's own voices |
| My progress | Avatar, AI level, right answers by level, **mastery per topic** (Attempted; Familiar >= 50%; Proficient >= 70% with >= 4 answers; Mastered >= 85% with >= 6), the path of the last 40 answers, badges (10 kinds), tests taken |

**How it works, for the jury**: `assets/como-funciona.html` (Spanish), served by the board at `/como-funciona.html`
and linked from the login pages: architecture diagram, the student journey, the hint ladder, the teacher's assistant,
each AI component with its evidence, the footprint on the board, privacy, design, limits and how to run it.

**Design references** (applied, not copied): Duolingo (session progress bar on top; pick an answer, then "Check";
a bottom bar with the verdict and one "Continue" button; 3D buttons), Khan Academy (4 mastery levels per topic:
Attempted, Familiar, Proficient, Mastered), Kahoot (each game answer has a colour and a shape; dark text on yellow),
WCAG 2.2 AA (text contrast >= 4.5:1, measured for every colour pair, which led to darker activity tiles; visible focus;
targets >= 44 px, AA asks 24), Material 3 (type roles, 48 dp touch targets), and teacher-dashboard research (lead with
the action: the summary opens with "What I'd do today", each action with its button). Bundled offline: the Nunito
font (OFL) and Lucide icons (ISC) as a sanitised SVG sprite (geometry only); see `assets/THIRD-PARTY-LICENSES.txt`.

Accessibility: text size (3 steps), high contrast, light/dark/auto theme, fewer animations,
sound on/off (Web Audio, no files), keyboard (A-E, H for hint, Enter), screen-reader live
regions, works on phones (tested at 390 px) and tablets.

## For the teacher: the AI assistant

Teacher PIN in `python/data/teacher_pin.txt` (random on first start, printed in the app log).

| Section | What it shows |
| --- | --- |
| AI summary | KPIs (students online, answers today, accuracy, median time per question, average level), **What I'd do today** (up to 4 actions, each with its button: see the students who need help, discuss a shared wrong answer in class, a practice test for the weakest family, move up the students who are ready) and **the assistant's report**: sentences generated from facts, in the teacher's language: who needs help, who may be guessing, who is dropping, who relies on hints, the family the class fails most, a wrong answer shared by several students (misconception), suggested support groups, the topics that take longest, the class's pace profiles with advice, problems harder than their level says, changes since the last snapshot, who never answered. One click turns a weak family into a practice test |
| Students | Sortable table: AI level and trend, right in the last 10, answers, median time, pace profile, weakest family, alerts. Each student: the assistant's sentences, level over time, recommended problems, latest answers with time and source, tests, badges, new PIN |
| Skills and groups | **Skills map**: students x semantic families, each cell right/answers coloured by how much better or worse than the model expected given the student's level and each problem's real difficulty (pale = fewer than 3 answers). **AI working groups**: k-means on the skills profiles, k chosen by the silhouette score (shown, with how well separated the groups are), each group with its needs, strengths and a one-click test. **Risk index**: an explainable sum of factors with their points (low accuracy, falling, guessing, hints, stuck, inactive, never started) |
| Response time | How it's measured; families and problems that take longest; the 5 pace profiles with what to do and who is in each; pace per student (x expected time) and where each is slowest |
| Question analysis | Classical psychometrics on the class's answers: % right, discrimination (correlation between getting it right and the student's level; only with >= 5 answers), and each wrong option with the average level of who chose it. Flags: negative discrimination, trap for strong students (a wrong option chosen by stronger students than the right one), too easy, too hard |
| AI reliability | The evidence for each model, measured on the board's own data (below) |
| Full report | Everything above in one printable document (print or save as PDF): KPIs, the assistant's report, skills map, groups, risk, time, questions to review, a line per student with a recommendation, and the reliability figures |
| Errors and concepts | Families the class fails (error rate, how many students, change since the last snapshot, most failed problem, practice set, "create a test"); shared wrong answers; problems harder/easier than their official level; snapshots; CSV |
| Tests | Create (title, level, questions, time limit, kind of problem = semantic family), open/close, results per student and per question |
| Games | The class's past games with their podiums |
| Class and PINs | Classes (create, rename, delete when empty), students (add: a random PIN shown once; new PIN; rename; delete), new PINs for the whole class and printable PIN cards |

How the assistant works (`python/insights.py`, all on the board):
1. **Ability (item response theory)**: 3PL with a fixed 20% guessing rate, P(right) = 0.2 + 0.8 / (1 + e^-(ability - difficulty)), fitted online like Elo (incrementally: only new answers are replayed). A problem's difficulty starts from its Kangaroo level and becomes what this class finds. A right answer after hints counts less (credit 0.75/0.5/0.25).
2. **Meaning (bge-m3 embeddings)**: 24 semantic families (spherical k-means), named by topic and distinctive words in each language.
3. **Time**: from when the question appears until the answer (reading the feedback doesn't count; capped at 10 min). Log-normal model: each answer's log-time minus the expected log-time for that problem (or its family). Speed = typical time / expected; with accuracy it gives the profile: confident (fast, right), thoughtful (slow, right), stuck (slow, wrong), impulsive (fast, wrong), struggling.
4. **Rules**: alerts (need help: < 30% in the last 10; guessing: median < 12 s and <= 30%; hints: >= 1.8 per answer; ready to go up: >= 80%; rising/falling: ability trend), shared misconceptions (the same wrong option chosen by >= 2 students), support groups (>= 2 students with the same weakest family).
5. **Skills map and groups** (`Insights.analysis`): per student and family, (right - expected right) / (answers + 2), where expected comes from the ability model; k-means (k-means++ start, fixed seed) on those vectors, k in 2-4 by silhouette.
6. **Question analysis**: point-biserial correlation of right/wrong with ability; distractor levels.

### Why it can be defended

| Component | Evidence (shown in "AI reliability", computed live) | Demo class (simulated, 15 Nov 2026) |
| --- | --- | --- |
| Ability model (IRT 3PL, online) | **Prequential evaluation**: every answer is predicted before the model learns from it (an out-of-sample test that needs no split), against two baselines. AUC, Brier, log-loss, accuracy, calibration curve and ECE | AUC 0.63 vs 0.57 (problem level only) vs 0.47 (student's own running accuracy); ECE 4.2%. The student's own accuracy is worse than chance because the adaptive trainer gives harder problems after right answers: a model that accounts for difficulty is needed |
| Semantic families (bge-m3 + spherical k-means) | Mean cosine within a family vs between families | 0.57 vs 0.49 (810 problems, 24 families) |
| Hints (language model; reference measured with Qwen3.5 0.8B) | Hints shown and how many gave the answer away (live); reference measurement on 725 validation problems | 6.3% leaked at the first try; 0 reach a student after the checks |
| Translations (SalamandraTA-7B) | 5 automatic checks per translation, threshold from a baseline (below) | see below |
| Report text | Template-based data-to-text: it can't invent facts. **Measured alternative**: the on-board LLM writing the summary from the same facts didn't invent numbers but distorted facts and mixed languages (2 of 4 drafts in our test), so the LLM is used only where its output is verified (hints, translations) | |

Limits (also on the page): uncertainty with few answers (nothing is flagged under 5 answers), one ability per student (the skills map adds per-family detail), automatic family names, time can't tell distraction from thinking (capped at 10 min), the demo class is simulated, and the assistant only suggests.

### Translations of the written solutions

The 396 written solutions are in English. `tools/translate_explanations.py` (laptop, once) translates them into Catalan
and Spanish with **SalamandraTA-7B-instruct v3** (Barcelona Supercomputing Center, a translation model; Q4_K_M GGUF
on the laptop GPU, prompt from its model card, temperature 0.1), and accepts a translation only if it passes:
numbers (the same numbers; an English ordinal "8th" may become "vuitè"/"octavo"), symbols (=, →, √, %, /, <, >, ×;
"x" between numbers is repaired back to ×), language (function words of the target language), length (0.6-1.9x),
and **meaning**: bge-m3 cosine between the English and the translation above the 99th percentile of cosines between
English solutions and unrelated translations (floor 0.70). A failed translation is retried sentence by sentence;
if it still fails, that problem keeps English and the page says so. Output: `python/data/explanations_i18n.json`
(merged by `coach.Bank`), `translation_report.json` (every score) and `translation_review.csv` (30 random items for a
person to judge). Run, on a laptop with an NVIDIA GPU and llama.cpp built with CUDA:

```bash
bash app/math-coach/deploy/get_models.sh salamandra && bash app/math-coach/deploy/get_models.sh bge-m3
~/llama.cpp/build-cuda/bin/llama-server -m ~/models/salamandraTA_7B_v3_q4_k_m.gguf -ngl 99 --jinja --port 8085 --ctx-size 4096 --parallel 1 &
~/llama.cpp/build-cuda/bin/llama-server -m ~/models/bge-m3-q8_0.gguf --embedding -ngl 99 --port 8084 --ctx-size 8192 \
    --batch-size 2048 --ubatch-size 2048 --parallel 1 &
python3 app/math-coach/tools/translate_explanations.py
```

SalamandraTA is GPL-3.0; it runs only on the laptop and is not shipped with the app.

Result (15 Nov 2026, RTX 4060 laptop, 20 min): **769 of 792 translations accepted (97.1%)**: 380/396 into Catalan,
389/396 into Spanish. Rejected: numbers 17 (mostly a number written as a word), symbols 3, meaning 2, language 1.
Meaning: median cosine 0.91 for the translations against 0.51 for unrelated pairs (99th percentile 0.65; threshold 0.70).
Spot check (by the assistant that built this, not yet by a person): 16 random accepted pairs all correct (one kept
"1.5" instead of "1,5"); of the 6 rejected for meaning, symbols or language, 3 were real errors (a corrupted brace,
two dropped arrows), 2 false alarms (a very short correct text; the Catalan pronoun "es" counted as Spanish, now
fixed in the checker) and 1 borderline. `translation_review.csv` is there for a person to give the official figure.

## How it's built

| Part | Where | What |
| --- | --- | --- |
| Problem map | `python/data/bank.json`, built by `build_bank.py` | 810 problems with 5 text options and no figure. Per problem: level, topic, text in eng/cat/esp, written solution (396), bge-m3 embedding (1024 dimensions). bge-m3 runs once on the laptop; the board only stores the vectors |
| Trainer | `coach.next_problem` | Right: nearest unseen problem one level up. Wrong: nearest unseen problem on the same topic, one level down. Never a near-copy (similarity >= 0.88) nor a problem the student saw solved |
| Hint ladder | `coach.rung1_..`, `rung2_..`, `rung3_..` | 1: nearest solved problem at a lower level, never with the same answer value. 2: topic and method. 3: one sentence from the language model (`sopa_z10` on the final board; measured with Qwen3.5 0.8B), rejected if it leaks the answer or teaches nothing; 2 tries, then the method. 4: the solution |
| School | `python/school.py` | Classes, students with hashed PINs and lockout, avatars, tests, test sessions, games, lessons done (SQLite) |
| AI assistant | `python/insights.py` | The models above; `student_report` and `class_report` return facts, the page writes the sentences |
| API | `python/main.py` | Token sessions for students and the teacher; practice, hints (one model worker, priority queue, cache, prefetch), tests, lessons, live rooms (in memory, a state machine lobby -> question -> reveal -> end), teacher endpoints. `ROUTES` is served by App Lab's web_ui brick on the board and by `dev_server.py` on a laptop |
| Page | `assets/index.html`, `styles.css`, `i18n.js`, `core.js`, `student.js`, `teacher.js`, `fonts/` | A single-page app without libraries: router, PIN pad, sounds, confetti, charts in HTML/SVG, ~530 texts in 3 languages, the Nunito font and a Lucide icon sprite (both bundled) |
| How it works | `assets/como-funciona.html` | The explainer page for the jury (Spanish), served by the board |
| Translations | `python/data/explanations_i18n.json`, made by `tools/translate_explanations.py` | The written solutions in Catalan and Spanish, only the ones that passed every check; `coach.Bank` merges them at start-up |
| LED matrix | `python/main.py` + `sketch/sketch.ino` | `?` and the level while answering, tick or cross after, `...` while the model writes |
| Model bridge | `board/llm_bridge.py` | App Lab runs the app in Docker; the bridge relays 172.17.0.1:8081 to the model on 127.0.0.1:8081 |

## Develop and demo on a laptop, without the board

`dev_server.py` serves the same API and page with the Python standard library (numpy is optional: without it the
semantic families fall back to the keyword topics). It needs `python/data/bank.json` (see the main README, step 2).
From the repository folder (Linux, macOS, or WSL on Windows, which is what we used):

```bash
# optional, for hint 3: the language model of setup step 5 on the laptop
~/llama.cpp/build/bin/llama-server -m ~/models/sopa_z10-Q8_0.gguf --port 8081 --ctx-size 4096 \
    --parallel 1 --cache-ram 0 --jinja --reasoning off --reasoning-budget 0 &

python3 app/math-coach/tools/seed_demo.py --db app/math-coach/python/data/profiles-demo.db --force   # a demo class
python3 app/math-coach/dev_server.py --port 7100 --db app/math-coach/python/data/profiles-demo.db       # http://127.0.0.1:7100
```

Every demo student's PIN is 1234; the teacher PIN is in `python/data/teacher_pin.txt` (made on the first start).
Without `--db` it uses an empty `python/data/profiles-dev.db`, never the class's `profiles.db`.

**Phones and tablets on the same Wi-Fi**: add `--host 0.0.0.0` and open `http://<laptop-ip>:7100` on them; the laptop's
firewall must allow TCP 7100 from the local network. On Windows with WSL (NAT networking) the port must also be
forwarded from Windows into WSL, as administrator: `netsh interface portproxy add v4tov4 listenport=7100
listenaddress=<laptop-ip> connectport=7100 connectaddress=<WSL ip>` plus an inbound firewall rule for TCP 7100 limited
to the local subnet. Some hotspots isolate their clients; then the devices can't reach each other.

`tools/seed_demo.py --db python/data/profiles-demo.db --force` (re)creates the demo: two classes,
16 simulated students over 7 days with behaviours for the assistant to find (a guesser, a stuck
student, one who relies on hints, one rising and one falling, three sharing a weak family, an
attractive wrong answer per problem, one who never logged in), a teacher test, games, lessons
and a snapshot. It refuses to write `profiles.db`.

## Install on the board

The full step-by-step is in the main README ("How to replicate"). In short, from a board set up with steps 0 to 12:

```bash
# 1. the problem map, python/data/bank.json (on the board or on a laptop; with bge-m3, pinned in config.env)
bash app/math-coach/deploy/get_models.sh bge-m3
~/llama.cpp/build/bin/llama-server -m ~/models/bge-m3-q8_0.gguf --embedding --port 8084 --ctx-size 8192 \
    --batch-size 2048 --ubatch-size 2048 --parallel 1 &
EMBED_PORT=8084 EMBED_QUERY_PREFIX="" EMBED_MAX_CHARS=6000 EMBED_NAME=bge-m3 python3 app/math-coach/build_bank.py
# 2. optional, on a laptop with a GPU: verified translations of the written solutions (see "Translations" above)
# 3. install and start: on the board ...
bash app/math-coach/deploy/install_on_board.sh
#    ... or from the laptop
bash app/math-coach/deploy/deploy_from_laptop.sh arduino@<board-ip>      # or: ... adb
```

`install_on_board.sh` copies `app.yaml`, the sketch, `python/*.py`, everything in `assets/` (including `fonts/`),
`python/data/bank.json` and, if it exists, `python/data/explanations_i18n.json` to `~/ArduinoApps/math-coach`; it
strips Windows line endings from the text files only (never from the fonts), installs the model bridge as a user
service, and (re)starts the app with `arduino-app-cli`. After a reboot: `install_on_board.sh --restart`.
The class data on the board (`python/data/profiles.db`) is never overwritten, and the board keeps its own teacher PIN
(`python/data/teacher_pin.txt` on the board, printed in the app log).

Students open `http://<board-ip>:7000` on the board's Wi-Fi (or `adb forward tcp:7000 tcp:7000`
and `http://127.0.0.1:7000` over USB); the explainer is at `http://<board-ip>:7000/como-funciona.html`.
Students from earlier versions are moved into a class "Classe 1" on first start; give them a PIN in
"Class and PINs". M3Kang is research-only: `python/data/` is git-ignored.

**Footprint** (measured on the laptop, 15 Nov 2026; to confirm on the board): the app is 6.1 MB on disk (code, page,
font, 810 problems with their vectors, translations) and uses 65 MB of RAM with the full teacher analysis; with the
language model (`sopa_z10` Q8_0, 1.83 GB, about 2.3 GB of RAM; it is the exam model, loaded once and shared) the total is under 1 GB of the 32 GB of storage and
about 1.1 GB of the 4 GB of RAM. SalamandraTA-7B (4.85 GB) and bge-m3 (0.63 GB) stay on the laptop.

## Tests and measurements

- `tools/smoke_platform.py`: the whole API in process (teacher, classes, PIN login and wrong PIN, practice with hints, tests with review, lessons, a 3-player game to the end, teacher reports, the complete analysis and the reliability figures, tests, snapshots). 0 failures. On the laptop the student calls take under 3 ms; with the 16-student demo class the teacher's overview takes about 80 ms, the complete analysis 50 ms and the reliability page 15 ms.
- `tools/multi_user_test.py --teacher-pin ...`: creates a test class, 4 students at once, then deletes it. On the laptop (15 Nov 2026): no errors, wrong PIN refused, answer + next problem 150 ms mean, rung 3 for 4 students asking at once 0.6-2.1 s on the laptop GPU.
- `tools/time_rungs.py --teacher-pin ...`: one student, rungs 1-3 and answers, with times.
- The incremental ability model gives exactly the same values as a full replay (checked after new answers and after deleting a student).

Earlier measurements (on the board, previous version, same trainer and ladder):

**Several students at once** (4 in parallel): start 170 ms, rung 1 46 ms, rung 2 40 ms, answer + next
problem 50 ms, ranking 14 ms. Rung 3 when all 4 ask at the same instant: 26, 47, 75, 106 s (the
model writes one at a time). **Prefetch** (a student reading rungs 1-2 for 25 s): rung 3 arrived in
0.0-0.1 s on 3 of 4 problems.

**Hint quality and leaks, whole validation set** (`tools/measure_hints.py`, Qwen3.5 0.8B Q8_0):
725 problems. Attempt 1: 46 leaked the answer (6.3%), 162 taught nothing (22.3%). After the second
try 49 (6.8%) are withheld and the student sees the topic's method. **Leaks shown to students: 0.**
Limit: a hint that passes can still be wrong.

**Rung 1 on all 810 problems** (`tools/measure_ladder.py`): same answer value as the problem
asked: 0. Same topic: 53%. With a written solution: 92%.

**Simulated students** (`tools/simulate_students.py`): the trainer settles at the right
boundary for students right below levels 2, 4 and 6. Levels 0 and 1 have only 29 and 27 text-only
problems; adding the problems with figures is the next step.

Limits: 23 of the 792 translated solutions failed a check and stay in English (the page says so). Live rooms
live in memory: a restart of the app ends the games in progress (results of finished games are saved).
