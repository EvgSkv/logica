# On Compiled vs. Interpreted Modes of Soufflé

  We additionally compare compiled and interpreted modes of Soufflé
  and observed a moderate speed up with compiled mode.

  Note that Soufflé reads input from CSV files while Logica reads from
  DuckDB. We do not consider this a significant factor since input data
  is very small and the complexity of the problems lies wholly in
  computing large output.

  Compiled benchmark notebook: `examples/graph/tgdk/benchmark_souffle.ipynb`
  Interpreted benchmark notebook: `examples/graph/tgdk/auxiliary/benchmark_souffle_interpreted.ipynb`

  **Transitive Closure:**

  | Graph | Interpreted (sec) | Compiled (sec) |
  |-------|-------------------|----------------|
  | g1k   | 0.67              | 0.58           |
  | g2k   | 1.97              | 1.73           |
  | g3k   | 4.46              | 3.61           |
  | g4k   | 8.29              | 6.98           |
  | g5k   | 13.03             | 10.96          |

  **Same Generation:**

  | Tree   | Interpreted (sec) | Compiled (sec) |
  |--------|-------------------|----------------|
  | tree7  | 0.24              | 0.24           |
  | tree8  | 0.30              | 0.29           |
  | tree9  | 0.68              | 0.62           |
  | tree10 | 4.37              | 3.94           |
  | tree11 | 29.76             | 26.25          |
  | tree12 | 175.14            | 153.46         |

  Environment: Soufflé 2.4, OpenMP enabled, 32-core machine, 125 GB RAM. Compiled
   mode: `souffle -o <binary> program.dl --jobs 32`, execution with `-j 32`.
  Compilation time excluded from measurements.
