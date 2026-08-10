#!/usr/bin/python
#
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Gradients of logix against JAX, in both execution modes.

Run: python3 -m common.logix_test
"""

import numpy as onp

if not __package__:
  import logix
else:
  from . import logix


M = onp.array([[1.0, 2.0], [3.0, 0.5]])
V = onp.array([2.0, 3.0])
IDX = onp.array([0, 0, 1])
U = onp.array([3.0, 3.0, 4.0])

# Every case exercises a gradient rule; ties in min/max check the
# even-split convention borrowed from JAX.
CASES = {
    'einsum': lambda np, p: np.sum(np.einsum('ab,b->a', M * p['w'], V)),
    'scatter_add': lambda np, p: np.sum(
        np.zeros(2).at[IDX].add(p['w'] * U) * V),
    'scatter_min_ties': lambda np, p: np.sum(
        np.full(2, np.inf).at[IDX].min(p['w'] * U)),
    'reduce_max_ties': lambda np, p: np.max(
        p['w'] * onp.array([1.0, 1.0, 0.5])),
    'where_pow': lambda np, p: np.sum(
        np.where(onp.array([True, False]), (p['w'] * V) ** 2,
                 p['w'] / V)),
    'gather': lambda np, p: np.sum((p['w'] * V)[onp.array([1, 1, 0])]),
    'min_initial': lambda np, p: np.sum(np.min(
        np.where(onp.array([[True, False], [False, False]]),
                 M * p['w'], np.inf), axis=1, initial=np.inf)),
    'minimum_elementwise': lambda np, p: np.sum(
        np.minimum(p['w'] * V, 4.0)),
    'exp_log': lambda np, p: np.sum(
        np.exp(p['w'] * 0.1) + np.log(p['w'] + 3.0)),
    'shape_shuffle': lambda np, p: np.sum(np.transpose(
        np.broadcast_to((p['w'] * V).reshape((2, 1)), (2, 3)),
        (1, 0)) * 2.0),
    'unrolled_loop': lambda np, p: np.sum(
        sum(p['w'] * V * i for i in range(1, 4))),
    'concatenate': lambda np, p: np.sum(np.concatenate(
        [p['w'] * V, (p['w'] ** 2) * V], axis=0) * onp.arange(4.0)),
}


def Run():
  try:
    import jax
  except ImportError:
    print('logix_test: JAX is not installed, nothing to compare with.')
    return 0
  jax.config.update('jax_enable_x64', True)
  import jax.numpy as jnp

  failures = 0
  for name, case in CASES.items():
    value, grads = jax.value_and_grad(
        lambda p: case(jnp, p))({'w': 2.0})
    expected = (float(value), onp.asarray(grads['w']))

    interpreted = logix.value_and_grad(
        lambda p: case(logix.numpy, p))({'w': 2.0})
    compiled_function = logix.jit(logix.value_and_grad(
        lambda p: case(logix.numpy, p)))
    compiled_function({'w': 2.0})  # Trace.
    compiled = compiled_function({'w': 2.0})  # The cached call.

    for mode, (value, grads) in [('interpreted', interpreted),
                                 ('compiled', compiled)]:
      actual = (float(value), onp.asarray(grads['w']))
      if (onp.allclose(actual[0], expected[0]) and
          onp.allclose(actual[1], expected[1])):
        continue
      failures += 1
      print('FAIL %s [%s]: jax %s, logix %s' % (
          name, mode, expected, actual))
  print('logix_test: %d cases, %d failures.' % (len(CASES), failures))
  return 1 if failures else 0


if __name__ == '__main__':
  import sys
  sys.exit(Run())
