#!/usr/bin/env python3
"""Run all TC/SG benchmarks on Logica and Nemo, collect times into CSV + ASCII table."""

import csv
import os
import re
import resource
import subprocess
import sys
import time


BENCHMARKS = [
    # (problem, dataset, csv_file)
    ("TC", "g1k", "g1k.csv"),
    ("TC", "g2k", "g2k.csv"),
    ("TC", "g3k", "g3k.csv"),
    ("TC", "g4k", "g4k.csv"),
    ("TC", "g5k", "g5k.csv"),
    ("SG", "tree7",  "tree7.csv"),
    ("SG", "tree8",  "tree8.csv"),
    ("SG", "tree9",  "tree9.csv"),
    ("SG", "tree10", "tree10.csv"),
    ("SG", "tree11", "tree11.csv"),
    ("SG", "tree12", "tree12.csv"),
]


LOGICA_TEMPLATES = {
    "TC": '''@Ground(G);
G(a, b) :- `("{csv}")`(a, b);

@Recursive(TC, ∞, stop: Stop);
TC(a, b) distinct :- G(a, b);
TC(a, c) distinct :- TC(a, b), G(b, c);

OldN() += 1 :- TC();
Stop() :- OldN() == Sum{{1 :- TC()}};

N() += 1 :- TC(a, b);
''',
    "SG": '''G(a, b) :- `("{csv}")`(a, b);

@Recursive(SG, -1, stop: Done);
SG(x, y) distinct :- G(a, x), G(a, y);
SG(x, y) distinct :- SG(a, b), G(a, x), G(b, y);
PrevSG(x, y) :- SG(x, y);
Done() :- Sum{{ 1 :- SG(x, y) }} == Sum{{ 1 :- PrevSG(x, y) }};

N() += 1 :- SG(x, y);
''',
}

NEMO_TEMPLATES = {
    "TC": '''@import edge :- csv{{resource="{csv}", ignore_headers=true}}.

TC(?A, ?B) :- edge(?A, ?B).
TC(?A, ?C) :- TC(?A, ?B), edge(?B, ?C).

N(#count(?A, ?B)) :- TC(?A, ?B).

@export N :- csv{{resource="n.csv"}}.
''',
    "SG": '''@import tree :- csv{{resource="{csv}", ignore_headers=true, format=(string,string)}}.

SG(?X, ?Y) :- tree(?A, ?X), tree(?A, ?Y).
SG(?X, ?Y) :- SG(?A, ?B), tree(?A, ?X), tree(?B, ?Y).

N(#count(?X, ?Y)) :- SG(?X, ?Y).

@export N :- csv{{resource="n.csv"}}.
''',
}


def generate_programs(problem, dataset, csv_file):
    """Write <problem>_<dataset>.l and .nemo files from templates."""
    base = f"{problem.lower()}_{dataset}"
    l_file = f"{base}.l"
    nemo_file = f"{base}.nemo"
    with open(l_file, "w") as f:
        f.write(LOGICA_TEMPLATES[problem].format(csv=csv_file))
    with open(nemo_file, "w") as f:
        f.write(NEMO_TEMPLATES[problem].format(csv=csv_file))
    return l_file, nemo_file


def run_timed(cmd):
    """Run a command, return (wall, user, sys, stdout, stderr)."""
    r0 = resource.getrusage(resource.RUSAGE_CHILDREN)
    t0 = time.time()
    proc = subprocess.run(cmd, capture_output=True, text=True)
    wall = time.time() - t0
    r1 = resource.getrusage(resource.RUSAGE_CHILDREN)
    user = r1.ru_utime - r0.ru_utime
    sys_t = r1.ru_stime - r0.ru_stime
    return wall, user, sys_t, proc.stdout, proc.stderr


def parse_logica_n(stdout):
    """Extract the N value from Logica's artistic_table output."""
    # Look for a number inside a table row like "| 12345 |"
    for line in stdout.splitlines():
        m = re.match(r"\|\s*(\d+)\s*\|", line)
        if m:
            return int(m.group(1))
    return None


def parse_nemo_n(results_path="results/n.csv"):
    """Nemo writes N to results/n.csv (one number per file)."""
    try:
        with open(results_path) as f:
            line = f.readline().strip().strip('"')
            return int(line)
    except (FileNotFoundError, ValueError):
        return None


def run_logica(l_file):
    cmd = ["python3", "logica/logica.py", l_file, "run_in_terminal", "N"]
    wall, user, sys_t, out, err = run_timed(cmd)
    n = parse_logica_n(out)
    return wall, user + sys_t, n


def run_nemo(nemo_file):
    cmd = ["nemo", nemo_file, "--overwrite-results"]
    wall, user, sys_t, out, err = run_timed(cmd)
    n = parse_nemo_n()
    return wall, user + sys_t, n


def ascii_table(rows, header):
    """Render rows as +---+---+ style table."""
    all_rows = [header] + [[str(c) for c in r] for r in rows]
    widths = [max(len(r[i]) for r in all_rows) for i in range(len(header))]
    sep = "+" + "+".join("-" * (w + 2) for w in widths) + "+"
    def fmt(r):
        return "| " + " | ".join(c.ljust(w) for c, w in zip(r, widths)) + " |"
    lines = [sep, fmt(header), sep]
    for r in all_rows[1:]:
        lines.append(fmt(r))
    lines.append(sep)
    return "\n".join(lines)


def main():
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    os.makedirs("results", exist_ok=True)

    rows = []
    for problem, dataset, csv_file in BENCHMARKS:
        print(f"=== {problem} {dataset} ===", flush=True)

        l_file, nemo_file = generate_programs(problem, dataset, csv_file)
        print(f"  Generated: {l_file}, {nemo_file}", flush=True)

        print(f"  Logica: {l_file}", flush=True)
        l_wall, l_cpu, l_n = run_logica(l_file)
        print(f"    wall={l_wall:.2f}s cpu={l_cpu:.2f}s N={l_n}", flush=True)

        print(f"  Nemo: {nemo_file}", flush=True)
        n_wall, n_cpu, n_n = run_nemo(nemo_file)
        print(f"    wall={n_wall:.2f}s cpu={n_cpu:.2f}s N={n_n}", flush=True)

        rows.append([
            problem, dataset,
            f"{l_wall:.2f}", f"{l_cpu:.2f}",
            f"{n_wall:.2f}", f"{n_cpu:.2f}",
            l_n if l_n is not None else "?",
            n_n if n_n is not None else "?",
        ])

    header = ["Problem", "Dataset",
              "Logica wall", "Logica CPU",
              "Nemo wall", "Nemo CPU",
              "Logica N", "Nemo N"]

    with open("benchmark_results.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)

    table = ascii_table(rows, header)
    with open("benchmark_results.txt", "w") as f:
        f.write(table + "\n")

    print()
    print(table)
    print()
    print("Wrote benchmark_results.csv and benchmark_results.txt")


if __name__ == "__main__":
    main()
