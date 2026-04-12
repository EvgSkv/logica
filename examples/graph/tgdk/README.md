# Benchmark Artifacts for "Logica-TGD: Transforming Graph Databases Logically"

This directory contains reproducible benchmark notebooks for the paper:

> **Logica-TGD: Transforming Graph Databases Logically**
> Evgeny Skvortsov, Yilin Xia, Bertram Ludäscher, Shawn Bowers
> *TGDK, 2026*

## Benchmarks

We compare three systems on graph computation problems (transitive closure,
pairwise distances, same generation):

- **Logica** — compiling to DuckDB SQL
- **Soufflé** — Datalog engine with parallel evaluation
- **DuckPGQ** — DuckDB extension implementing SQL/PGQ (Cypher-style queries)

All benchmarks were run on a Google Cloud **c2d-standard-32** instance
(32 vCPUs, 128 GB RAM).

### Main notebooks

| Notebook | Description |
|----------|-------------|
| `benchmark_logica.ipynb` | Logica benchmarks (all problems). **Run this first** — it generates input data (CSV files and `graphs.db`) used by the other notebooks. |
| `benchmark_souffle.ipynb` | Soufflé benchmarks (compiled mode) |
| `benchmark_cypher.ipynb` | DuckPGQ / Cypher benchmarks |

### Auxiliary materials

| File | Description |
|------|-------------|
| `auxiliary/benchmark_souffle_interpreted.ipynb` | Soufflé benchmarks in interpreted mode (used in the original submission) |
| `auxiliary/benchmark_logica_with_output_sizes.ipynb` | Logica notebook computing output sizes for the table in the paper |
| `auxiliary/souffle_compiled_vs_interpreted.md` | Comparison of Soufflé compiled vs. interpreted modes |

## Reproducing the results

1. Install Jupyter Notebook:
   ```
   python3 -m pip install notebook
   ```

2. Install DuckDB:
   ```
   python3 -m pip install duckdb
   ```

3. Install Soufflé (v2.4 was used) by following the instructions at
   [souffle-lang.github.io](https://souffle-lang.github.io/install).

4. Clone this repository:
   ```
   git clone https://github.com/EvgSkv/logica
   ```

5. Start the notebook server from the repository root, so that Logica
   is importable:
   ```
   cd logica
   python3 -m notebook examples/graph/tgdk
   ```
   Alternatively, install Logica with `python3 -m pip install logica` and start
   the notebook from anywhere.

6. Run the notebooks starting with `benchmark_logica.ipynb` — it
   generates the input data (CSV files and `graphs.db`) used by the
   Soufflé and DuckPGQ notebooks. Then proceed to `benchmark_souffle.ipynb`
   and `benchmark_cypher.ipynb`.
