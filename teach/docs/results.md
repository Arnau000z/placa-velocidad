# Results: full tables

All tables were computed from the run files in `results/` (git-ignored, they hold problem ids), with
`Qwen3.5 0.8B Q8_0`, on 15 Nov 2026. They show aggregates only: no problem text, no ids.

- The 4 runs with 50 problems are the first smoke tests (on the laptop CPU). In the run named `rag3`, `rag_k` was
  still 1 (a naming slip).
- The runs ending in `-gpu`, and the bge-m3 runs, used the same model and settings on a laptop GPU, for speed.
- The calc-mode run stopped at 717 of 789 problems and is not in `ablations.csv`; its accuracy is computed from its
  run file.
- "lv0-4" runs use levels 0 to 4 only (393 problems). The baseline on those levels is 26.5%.

Topics are the app's keyword topics (`coach.classify_topic`) on the English text. Problems with no rule match go to
"Arithmetic and word problems".

The hint table comes from `tools/measure_hints.py` (the same prompt and checks as the app). "Taught nothing" means
the hint repeated the problem or was too short.
### Experiments (results/ablations.csv), same model Qwen3.5 0.8B Q8_0

| Run | Problems | RAG examples | Accuracy | vs baseline |
| --- | ---: | ---: | ---: | ---: |
| baseline | 50 | 0 | 26.0% |  |
| baseline | 50 | 0 | 26.0% |  |
| rag1 | 50 | 1 | 26.0% |  |
| rag3 | 50 | 1 | 26.0% |  |
| cmp-letter-gpu | 789 | 0 | 21.3% | +0.0 |
| cmp-value-gpu | 789 | 0 | 17.1% | -4.2 |
| cmp-rag1-full-gpu | 789 | 1 | 23.7% | +2.4 |
| cmp-rag1-letter-gpu | 789 | 1 | 23.1% | +1.8 |
| cmp-rag1-value-gpu | 789 | 1 | 25.6% | +4.3 |
| m3-rag3-plain | 789 | 3 | 26.9% | +5.6 |
| m3-rag3-value | 789 | 3 | 27.2% | +5.9 |
| small-rag3 | 789 | 3 | 25.6% | +4.3 |
| m3-rag3-value-lv0-4 | 393 | 3 | 31.3% |  |
| m3-rag3-explained-lv0-4 | 393 | 3 | 34.6% |  |
| cmp-calc-gpu (not in ablations.csv: stopped at 717/789) | 717 | 0 | 22.7% | |

### Error analysis (validation set, 789 problems in 3 languages)

#### By language

|  | baseline (letter, no RAG) | best (bge-m3 RAG 3, value examples) | problems |
| --- | ---: | ---: | ---: |
| English | 22.4% | 27.4% | 281 |
| Catalan | 21.4% | 28.5% | 281 |
| Spanish | 19.8% | 25.6% | 227 |

#### By level (0 easiest, 7 hardest)

|  | baseline (letter, no RAG) | best (bge-m3 RAG 3, value examples) | problems |
| --- | ---: | ---: | ---: |
| 0 | 38.2% | 41.8% | 55 |
| 1 | 34.0% | 27.7% | 47 |
| 2 | 29.5% | 33.3% | 78 |
| 3 | 8.6% | 31.4% | 35 |
| 4 | 23.0% | 28.1% | 178 |
| 5 | 21.5% | 31.5% | 149 |
| 6 | 10.9% | 21.0% | 138 |
| 7 | 15.6% | 14.7% | 109 |

#### By topic (keyword topics of the app, on the English text)

|  | baseline (letter, no RAG) | best (bge-m3 RAG 3, value examples) | problems |
| --- | ---: | ---: | ---: |
| Ages | 13.3% | 13.3% | 15 |
| Arithmetic and word problems | 20.6% | 29.4% | 160 |
| Certainty and worst cases | 0.0% | 0.0% | 11 |
| Counting and combinations | 22.2% | 48.1% | 27 |
| Logic: who tells the truth | 0.0% | 16.7% | 18 |
| Digits and divisibility | 28.6% | 25.3% | 91 |
| Sequences and patterns | 40.0% | 13.3% | 15 |
| Lengths, areas and angles | 24.7% | 31.0% | 287 |
| Fractions, percentages and averages | 9.8% | 43.9% | 41 |
| Cubes, dice and solids | 15.6% | 12.2% | 90 |
| Speed and distance | 17.4% | 8.7% | 23 |
| Clocks, time and calendars | 18.2% | 45.5% | 11 |

#### Text-only problems vs problems that need a figure

|  | baseline (letter, no RAG) | best (bge-m3 RAG 3, value examples) | problems |
| --- | ---: | ---: | ---: |
| needs the figure | 22.5% | 28.0% | 440 |
| text only | 19.8% | 26.4% | 349 |

#### Letter bias (answers given vs true answers, baseline)

| Letter | A | B | C | D | E |
| --- | ---: | ---: | ---: | ---: | ---: |
| Given by the model | 169 | 63 | 8 | 511 | 38 |
| True answer | 157 | 173 | 148 | 179 | 132 |

### Hint ladder, rung 3 (tools/measure_hints.py, 725 validation problems)

| Group | Problems | Attempt 1: gave the answer away | Attempt 1: taught nothing | Attempt 2 also rejected (method shown instead) | Model hint shown |
| --- | ---: | ---: | ---: | ---: | ---: |
| All | 725 | 6.3% | 22.3% | 6.8% | 93.2% |
| English | 256 | 5.9% | 16.0% | 4.3% | 95.7% |
| Catalan | 256 | 5.1% | 30.5% | 7.8% | 92.2% |
| Spanish | 213 | 8.5% | 20.2% | 8.5% | 91.5% |
| Level 0 | 42 | 4.8% | 19.0% | 2.4% | 97.6% |
| Level 1 | 41 | 7.3% | 19.5% | 7.3% | 92.7% |
| Level 2 | 62 | 4.8% | 9.7% | 4.8% | 95.2% |
| Level 3 | 32 | 0.0% | 21.9% | 6.2% | 93.8% |
| Level 4 | 171 | 7.0% | 26.3% | 9.4% | 90.6% |
| Level 5 | 144 | 9.7% | 25.0% | 7.6% | 92.4% |
| Level 6 | 135 | 5.2% | 23.0% | 6.7% | 93.3% |
| Level 7 | 98 | 5.1% | 21.4% | 4.1% | 95.9% |
