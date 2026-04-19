# Benchmark Artifacts for "Logica-TGD: Transforming Graph Databases Logically"

This directory contains reproducible benchmark notebooks for the paper:

> **Logica-TGD: Transforming Graph Databases Logically**
> Evgeny Skvortsov, Yilin Xia, Bertram Ludäscher, Shawn Bowers
> *TGDK, 2026*

## Benchmarks

We compare four systems on graph computation problems (transitive closure,
pairwise distances, same generation):

- **Logica** — compiling to DuckDB SQL
- **Soufflé** — Datalog engine with parallel evaluation
- **DuckPGQ** — DuckDB extension implementing SQL/PGQ (Cypher-style queries)
- **Nemo** — single-threaded Rust rule engine (for the Nemo column only)

All benchmarks were run on a Google Cloud **c2d-standard-32** instance
(32 vCPUs, 128 GB RAM) using Logica 1.3.1415926535897, DuckDB 1.3.2,
Soufflé 2.4, and Nemo 0.10.0.

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

### Nemo comparison

| File | Description |
|------|-------------|
| `benchmark_and_collect.py` | Runs all TC and SG benchmarks on both Logica and Nemo, collects wall/CPU times and fact counts into `benchmark_results.txt` (ASCII table) and `benchmark_results.csv`. Generates the `.l` and `.nemo` programs from templates. |
| `tc_g1k.l`, `tc_g1k.nemo` | Example Logica and Nemo programs for transitive closure (shown for reference — the script regenerates all sizes). |
| `sg_tree7.l`, `sg_tree7.nemo` | Example Logica and Nemo programs for same generation. |
| `benchmark_results.txt` | Output of `benchmark_and_collect.py` from our run. |

To run the Nemo comparison:

1. Install Nemo 0.10.0 (see [nemo rule engine](https://github.com/knowsys/nemo)).
   The `nmo` binary must be on `PATH` (we invoke it as `nemo` in the script —
   adjust the command there if your binary is named `nmo`).
2. Make sure the CSV inputs (`g1k.csv`..`g5k.csv`, `tree7.csv`..`tree12.csv`)
   are present in the same directory. They are produced by running
   `benchmark_logica.ipynb`.
3. Run the script from this directory:
   ```
   python3 benchmark_and_collect.py
   ```
   It writes `benchmark_results.txt` and `benchmark_results.csv`.

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
