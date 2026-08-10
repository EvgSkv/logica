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

"""Logix: a pure-numpy tensor engine with reverse-mode autodiff.

A drop-in stand-in for the jax / jax.numpy pair within the neural
fragment: where the code says `import jax; import jax.numpy as jnp`,
say `from common import logix as jax; jnp = jax.numpy` instead. Exists
so that neural execution runs where jaxlib does not build — first of
all Pyodide in the browser.

Design: an eager tape. Every operation computes immediately in numpy
and returns a Tensor. When a tape is active (inside value_and_grad or a
jit trace) and an argument descends from a differentiated leaf, a node
is also recorded. Gradient rules build their result via the same public
operations, so the backward pass lands on the same tape — one
definition of each rule serves both execution modes:

  * interpreted — value_and_grad builds the tape and evaluates it as it
    goes; nothing else happens. Slow, simple, the reference.
  * compiled — jit traces one call, then serializes the tape into a
    straight-line numpy function (the graphs of the neural fragment are
    static). exec() once, reuse every call. LOGIX_JIT=0 disables.

Tie-breaking in min/max gradients copies JAX: the cotangent of a cell
is split evenly among the positions achieving the extremum.
"""

import contextlib
import os
import threading
import types

import numpy as onp


class LogixError(TypeError):
  pass


_STATE = threading.local()


def _Tape():
  return getattr(_STATE, 'tape', None)


class Node(object):
  """One computed value: an op applied to arguments.

  args hold Nodes and plain python constants (numpy arrays, scalars,
  strings, shape tuples); only recorded Node arguments carry gradients.
  index is the position on the tape, or None for a free (constant)
  node."""
  __slots__ = ('op', 'args', 'value', 'index')

  def __init__(self, op, args, value, index=None):
    self.op = op
    self.args = args
    self.value = value
    self.index = index

  @property
  def recorded(self):
    return self.index is not None


class Tensor(object):
  """User-facing box around a node; duck-types a jax array."""
  __slots__ = ('node',)

  # Refuse numpy's own ufunc dispatch: a plain-numpy left operand must
  # defer to our reflected operators, or tracing is silently lost.
  __array_ufunc__ = None

  def __init__(self, node):
    self.node = node

  @property
  def value(self):
    return self.node.value

  def __array__(self, dtype=None):
    result = onp.asarray(self.node.value)
    return result.astype(dtype) if dtype is not None else result

  @property
  def shape(self):
    return onp.shape(self.node.value)

  @property
  def ndim(self):
    return onp.ndim(self.node.value)

  @property
  def size(self):
    return onp.size(self.node.value)

  @property
  def dtype(self):
    return onp.asarray(self.node.value).dtype

  @property
  def at(self):
    return _At(self)

  def reshape(self, *shape):
    if len(shape) == 1 and isinstance(shape[0], (tuple, list)):
      shape = tuple(shape[0])
    return _Record('reshape', [self, tuple(shape)])

  def transpose(self, axes):
    return _Record('transpose', [self, tuple(axes)])

  def astype(self, dtype):
    return _Record('astype', [self, onp.dtype(dtype)])

  def sum(self, axis=None):
    return numpy.sum(self, axis=axis)

  def copy(self):
    return self

  def __getitem__(self, index):
    return _Record('gather', [self, _FreezeIndex(index)])

  def __len__(self):
    return len(self.node.value)

  def __float__(self):
    return float(self.node.value)

  def __int__(self):
    return int(self.node.value)

  def __bool__(self):
    return bool(self.node.value)

  def __repr__(self):
    return 'Tensor(%r)' % (self.node.value,)

  def __neg__(self):
    return _Record('neg', [self])

  def __invert__(self):
    return _Record('logical_not', [self])

  def __add__(self, other):
    return _Record('add', [self, other])

  def __radd__(self, other):
    return _Record('add', [other, self])

  def __sub__(self, other):
    return _Record('sub', [self, other])

  def __rsub__(self, other):
    return _Record('sub', [other, self])

  def __mul__(self, other):
    return _Record('mul', [self, other])

  def __rmul__(self, other):
    return _Record('mul', [other, self])

  def __truediv__(self, other):
    return _Record('div', [self, other])

  def __rtruediv__(self, other):
    return _Record('div', [other, self])

  def __pow__(self, other):
    return _Record('pow', [self, other])

  def __rpow__(self, other):
    return _Record('pow', [other, self])

  def __mod__(self, other):
    return _Record('mod', [self, other])

  def __eq__(self, other):
    return _Record('eq', [self, other])

  def __ne__(self, other):
    return _Record('ne', [self, other])

  def __lt__(self, other):
    return _Record('lt', [self, other])

  def __le__(self, other):
    return _Record('le', [self, other])

  def __gt__(self, other):
    return _Record('gt', [self, other])

  def __ge__(self, other):
    return _Record('ge', [self, other])

  def __and__(self, other):
    return _Record('logical_and', [self, other])

  def __rand__(self, other):
    return _Record('logical_and', [other, self])

  def __or__(self, other):
    return _Record('logical_or', [self, other])

  def __ror__(self, other):
    return _Record('logical_or', [other, self])

  __hash__ = None


class _AtIndex(object):
  __slots__ = ('tensor', 'index')

  def __init__(self, tensor, index):
    self.tensor = tensor
    self.index = index

  def add(self, updates):
    return _Record('scatter_add', [self.tensor, self.index, updates])

  def min(self, updates):
    return _Record('scatter_min', [self.tensor, self.index, updates])

  def max(self, updates):
    return _Record('scatter_max', [self.tensor, self.index, updates])

  def set(self, updates):
    return _Record('scatter_set', [self.tensor, self.index, updates])


class _At(object):
  __slots__ = ('tensor',)

  def __init__(self, tensor):
    self.tensor = tensor

  def __getitem__(self, index):
    return _AtIndex(self.tensor, _FreezeIndex(index))


def _FreezeIndex(index):
  """Indices are static data, never differentiated through."""
  if isinstance(index, Tensor):
    return onp.asarray(index.node.value)
  if isinstance(index, tuple):
    return tuple(onp.asarray(i.node.value) if isinstance(i, Tensor) else i
                 for i in index)
  return index


def _Value(x):
  return x.node.value if isinstance(x, Tensor) else x


def _Record(op, args):
  """Computes op eagerly; records a node when the result is traced."""
  values = [_Value(a) for a in args]
  # Masked-out cells legitimately hold inf/nan garbage that a later
  # `where` discards; their floating-point warnings are pure noise.
  with onp.errstate(invalid='ignore', divide='ignore', over='ignore'):
    value = _FORWARD[op](*values)
  tape = _Tape()
  traced = tape is not None and any(
      isinstance(a, Tensor) and a.node.recorded for a in args)
  node_args = [a.node if isinstance(a, Tensor) else a for a in args]
  if traced:
    node = Node(op, node_args, value, len(tape))
    tape.append(node)
  else:
    node = Node(op, node_args, value)
  return Tensor(node)


def _Constant(value):
  return Tensor(Node('const', [], value))


###############################################################################
# Forward implementations.

def _ScatterForward(update_in_place):
  def Forward(target, index, updates):
    result = onp.array(target)
    update_in_place(result, index, updates)
    return result
  return Forward


def _ExtremumForward(reduction):
  def Forward(x, axis=None, keepdims=False, initial=None):
    kwargs = {'axis': axis, 'keepdims': keepdims}
    if initial is not None:
      kwargs['initial'] = initial
    return reduction(x, **kwargs)
  return Forward


_FORWARD = {
    'const': None,
    'leaf': None,
    'add': onp.add,
    'sub': onp.subtract,
    'mul': onp.multiply,
    'div': onp.divide,
    'pow': onp.power,
    'mod': onp.mod,
    'neg': onp.negative,
    'abs': onp.abs,
    'exp': onp.exp,
    'log': onp.log,
    'sqrt': onp.sqrt,
    'sin': onp.sin,
    'cos': onp.cos,
    'floor': onp.floor,
    'eq': onp.equal,
    'ne': onp.not_equal,
    'lt': onp.less,
    'le': onp.less_equal,
    'gt': onp.greater,
    'ge': onp.greater_equal,
    'logical_and': onp.logical_and,
    'logical_or': onp.logical_or,
    'logical_not': onp.logical_not,
    'minimum': onp.minimum,
    'maximum': onp.maximum,
    'where': lambda c, a, b: onp.where(c, a, b),
    'einsum': lambda spec, *ops: onp.einsum(spec, *ops),
    'gather': lambda x, index: onp.asarray(x)[index],
    'scatter_add': _ScatterForward(onp.add.at),
    'scatter_min': _ScatterForward(onp.minimum.at),
    'scatter_max': _ScatterForward(onp.maximum.at),
    'scatter_set': _ScatterForward(
        lambda result, index, updates: result.__setitem__(index, updates)),
    'sum': lambda x, axis=None, keepdims=False: onp.sum(
        x, axis=axis, keepdims=keepdims),
    'prod': lambda x, axis=None, keepdims=False: onp.prod(
        x, axis=axis, keepdims=keepdims),
    'min': _ExtremumForward(onp.min),
    'max': _ExtremumForward(onp.max),
    'any': lambda x, axis=None: onp.any(x, axis=axis),
    'broadcast_to': onp.broadcast_to,
    'reshape': lambda x, shape: onp.reshape(x, shape),
    'transpose': lambda x, axes: onp.transpose(x, axes),
    'expand_dims': lambda x, axis: onp.expand_dims(x, axis),
    'astype': lambda x, dtype: onp.asarray(x).astype(dtype),
    'concatenate': lambda axis, *parts: onp.concatenate(parts, axis=axis),
    'lexsort': lambda axis, *keys: onp.lexsort(keys, axis=axis),
    'sort': lambda x, axis: onp.sort(x, axis=axis),
    'take_along_axis': lambda a, index, axis: onp.take_along_axis(
        a, index, axis=axis),
}


###############################################################################
# Gradient rules.
#
# A rule receives the node and the cotangent g (a Tensor or a numpy
# array) and returns a cotangent per argument, None for the
# non-differentiable ones. Rules compute via the public operations, so
# their work lands on the active tape — this is what lets the compiled
# mode serialize the backward pass without a second definition.


def _TensorOf(arg):
  return Tensor(arg) if isinstance(arg, Node) else arg


def _ShapeOf(arg):
  return onp.shape(arg.value if isinstance(arg, Node) else arg)


def _Unbroadcast(g, shape):
  """Sums g down to `shape` after numpy broadcasting."""
  g_shape = onp.shape(_Value(g))
  if g_shape == tuple(shape):
    return g
  extra = len(g_shape) - len(shape)
  if extra > 0:
    g = numpy.sum(g, axis=tuple(range(extra)))
  axes = tuple(i for i, n in enumerate(shape)
               if n == 1 and onp.shape(_Value(g))[i] != 1)
  if axes:
    g = numpy.sum(g, axis=axes, keepdims=True)
  return g


def _GradBinary(da, db):
  def Rule(node, g):
    a, b = node.args
    ga = _Unbroadcast(da(g, a, b), _ShapeOf(a)) if _Recorded(a) else None
    gb = _Unbroadcast(db(g, a, b), _ShapeOf(b)) if _Recorded(b) else None
    return [ga, gb]
  return Rule


def _Recorded(arg):
  return isinstance(arg, Node) and arg.recorded


def _GradPowBase(g, a, b):
  base, power = _TensorOf(a), _TensorOf(b)
  return g * power * base ** (power - 1.0)


def _GradPowExponent(g, a, b):
  base, power = _TensorOf(a), _TensorOf(b)
  return g * base ** power * numpy.log(base)


def _GradEinsum(node, g):
  spec = node.args[0]
  operands = node.args[1:]
  inputs, output = spec.split('->')
  inputs = inputs.split(',')
  grads = [None]
  for position, operand in enumerate(operands):
    if not _Recorded(operand):
      grads.append(None)
      continue
    other_specs = [s for i, s in enumerate(inputs) if i != position]
    other_operands = [_TensorOf(o) for i, o in enumerate(operands)
                      if i != position]
    back_spec = ','.join([output] + other_specs) + '->' + inputs[position]
    grads.append(numpy.einsum(back_spec, g, *other_operands))
  return grads


def _GradWhere(node, g):
  condition = _TensorOf(node.args[0])
  ga, gb = None, None
  if _Recorded(node.args[1]):
    ga = _Unbroadcast(numpy.where(condition, g, 0.0),
                      _ShapeOf(node.args[1]))
  if _Recorded(node.args[2]):
    gb = _Unbroadcast(numpy.where(condition, 0.0, g),
                      _ShapeOf(node.args[2]))
  return [None, ga, gb]


def _GradGather(node, g):
  x, index = node.args
  if not _Recorded(x):
    return [None, None]
  zeros = numpy.zeros(_ShapeOf(x), dtype=onp.float64)
  return [zeros.at[index].add(g), None]


def _GradScatterAdd(node, g):
  target, index, updates = node.args
  gt = g if _Recorded(target) else None
  gu = g[index] if _Recorded(updates) else None
  return [gt, None, gu]


def _GradScatterExtremum(node, g):
  target, index, updates = node.args
  result = Tensor(node)
  update_wins = (_TensorOf(updates) == result[index]).astype(onp.float64)
  target_wins = (_TensorOf(target) == result).astype(onp.float64)
  counts = numpy.zeros(_ShapeOf(target),
                       dtype=onp.float64).at[index].add(update_wins)
  counts = counts + target_wins
  cell_share = g / numpy.where(counts > 0.0, counts, 1.0)
  gt = (cell_share * target_wins) if _Recorded(target) else None
  gu = (cell_share[index] * update_wins) if _Recorded(updates) else None
  return [gt, None, gu]


def _GradScatterSet(node, g):
  target, index, updates = node.args
  gt = None
  if _Recorded(target):
    gt = g.at[index].set(onp.zeros(onp.shape(_Value(g)[index])))
  gu = g[index] if _Recorded(updates) else None
  return [gt, None, gu]


def _NormalizeAxes(axis, ndim):
  if axis is None:
    return tuple(range(ndim))
  if isinstance(axis, int):
    return (axis % ndim,)
  return tuple(a % ndim for a in axis)


def _KeepDims(reduced, x_shape, axes):
  """Reinserts reduced axes as size 1 for broadcasting back."""
  shape = list(x_shape)
  for a in axes:
    shape[a] = 1
  return numpy.reshape(reduced, tuple(shape))


def _GradSum(node, g):
  x, axis, keepdims = node.args
  if not _Recorded(x):
    return [None, None, None]
  x_shape = _ShapeOf(x)
  axes = _NormalizeAxes(axis, len(x_shape))
  if not keepdims:
    g = _KeepDims(g, x_shape, axes)
  return [numpy.broadcast_to(g, x_shape), None, None]


def _GradExtremum(node, g):
  x, axis, keepdims, unused_initial = node.args
  if not _Recorded(x):
    return [None, None, None, None]
  x_shape = _ShapeOf(x)
  axes = _NormalizeAxes(axis, len(x_shape))
  result = Tensor(node)
  if not keepdims:
    result = _KeepDims(result, x_shape, axes)
    g = _KeepDims(g, x_shape, axes)
  # Winners share the cotangent evenly (as in JAX); a cell decided
  # purely by `initial` has no winners and passes no gradient.
  wins = (_TensorOf(x) == result).astype(onp.float64)
  counts = numpy.sum(wins, axis=axes, keepdims=True)
  share = g / numpy.where(counts > 0.0, counts, 1.0)
  return [wins * share, None, None, None]


def _GradElementwiseExtremum(node, g):
  a, b = node.args
  result = Tensor(node)
  left, right = _TensorOf(a), _TensorOf(b)
  left_wins = (left == result)
  right_wins = (right == result)
  share = numpy.where(left_wins & right_wins, g * 0.5, g)
  ga, gb = None, None
  if _Recorded(a):
    ga = _Unbroadcast(numpy.where(left_wins, share, 0.0), _ShapeOf(a))
  if _Recorded(b):
    gb = _Unbroadcast(numpy.where(right_wins, share, 0.0), _ShapeOf(b))
  return [ga, gb]


def _GradBroadcastTo(node, g):
  x, unused_shape = node.args
  if not _Recorded(x):
    return [None, None]
  return [_Unbroadcast(g, _ShapeOf(x)), None]


def _GradReshape(node, g):
  x, unused_shape = node.args
  if not _Recorded(x):
    return [None, None]
  return [numpy.reshape(g, _ShapeOf(x)), None]


def _GradTranspose(node, g):
  x, axes = node.args
  if not _Recorded(x):
    return [None, None]
  inverse = tuple(int(i) for i in onp.argsort(axes))
  return [numpy.transpose(g, inverse), None]


def _GradExpandDims(node, g):
  x, unused_axis = node.args
  if not _Recorded(x):
    return [None, None]
  return [numpy.reshape(g, _ShapeOf(x)), None]


def _GradConcatenate(node, g):
  axis = node.args[0]
  parts = node.args[1:]
  grads = [None]
  offset = 0
  for part in parts:
    size = _ShapeOf(part)[axis]
    if _Recorded(part):
      index = [slice(None)] * len(onp.shape(_Value(g)))
      index[axis] = slice(offset, offset + size)
      grads.append(g[tuple(index)])
    else:
      grads.append(None)
    offset += size
  return grads


def _GradAstype(node, g):
  x, dtype = node.args
  if not _Recorded(x) or not onp.issubdtype(onp.dtype(dtype),
                                            onp.floating):
    return [None, None]
  original = onp.asarray(x.value).dtype
  if not onp.issubdtype(original, onp.floating):
    return [None, None]
  return [_TensorOf(g).astype(original) if isinstance(g, Tensor)
          else onp.asarray(g).astype(original), None]


def _GradUnary(derivative):
  def Rule(node, g):
    a = node.args[0]
    if not _Recorded(a):
      return [None]
    return [derivative(g, _TensorOf(a), Tensor(node))]
  return Rule


_GRAD = {
    'add': _GradBinary(lambda g, a, b: g, lambda g, a, b: g),
    'sub': _GradBinary(lambda g, a, b: g, lambda g, a, b: -g),
    'mul': _GradBinary(lambda g, a, b: g * _TensorOf(b),
                       lambda g, a, b: g * _TensorOf(a)),
    'div': _GradBinary(
        lambda g, a, b: g / _TensorOf(b),
        lambda g, a, b: -g * _TensorOf(a) / (_TensorOf(b) * _TensorOf(b))),
    'pow': _GradBinary(_GradPowBase, _GradPowExponent),
    'neg': _GradUnary(lambda g, a, y: -g),
    'abs': _GradUnary(lambda g, a, y: g * numpy.where(a < 0.0, -1.0, 1.0)),
    'exp': _GradUnary(lambda g, a, y: g * y),
    'log': _GradUnary(lambda g, a, y: g / a),
    'sqrt': _GradUnary(lambda g, a, y: g * 0.5 / y),
    'sin': _GradUnary(lambda g, a, y: g * numpy.cos(a)),
    'cos': _GradUnary(lambda g, a, y: -g * numpy.sin(a)),
    'floor': _GradUnary(lambda g, a, y: g * 0.0),
    'minimum': _GradElementwiseExtremum,
    'maximum': _GradElementwiseExtremum,
    'where': _GradWhere,
    'einsum': _GradEinsum,
    'gather': _GradGather,
    'scatter_add': _GradScatterAdd,
    'scatter_min': _GradScatterExtremum,
    'scatter_max': _GradScatterExtremum,
    'scatter_set': _GradScatterSet,
    'sum': _GradSum,
    'min': _GradExtremum,
    'max': _GradExtremum,
    'broadcast_to': _GradBroadcastTo,
    'reshape': _GradReshape,
    'transpose': _GradTranspose,
    'expand_dims': _GradExpandDims,
    'astype': _GradAstype,
    'concatenate': _GradConcatenate,
    # lexsort, sort, prod and take_along_axis carry no gradient:
    # sorting indices, permutations and rank keys of bit-valued data.
}


###############################################################################
# The jnp-like namespace.


def _MakeNumpy():
  ns = types.ModuleType('logix.numpy')
  ns.float64 = onp.float64
  ns.int64 = onp.int64
  ns.bool_ = onp.bool_
  ns.inf = onp.inf

  def Constructor(name):
    def Call(*args, **kwargs):
      args = [_Value(a) for a in args]
      return _Constant(getattr(onp, name)(*args, **kwargs))
    return Call

  for name in ['array', 'asarray', 'zeros', 'ones', 'full', 'arange']:
    setattr(ns, name, Constructor(name))

  def Unary(op):
    return lambda x: _Record(op, [x])

  for op in ['abs', 'exp', 'log', 'sqrt', 'sin', 'cos', 'floor',
             'logical_not']:
    setattr(ns, op, Unary(op))

  def Binary(op):
    return lambda a, b: _Record(op, [a, b])

  for op in ['minimum', 'maximum', 'logical_and', 'logical_or']:
    setattr(ns, op, Binary(op))
  ns.add = Binary('add')

  ns.where = lambda c, a, b: _Record('where', [c, a, b])
  ns.einsum = lambda spec, *ops: _Record('einsum', [spec] + list(ops))
  ns.broadcast_to = lambda x, shape: _Record(
      'broadcast_to', [x, tuple(shape)])
  ns.reshape = lambda x, shape: _Record(
      'reshape', [x, tuple(shape) if isinstance(shape, (tuple, list))
                  else shape])
  ns.transpose = lambda x, axes=None: _Record(
      'transpose', [x, tuple(axes) if axes is not None else
                    tuple(reversed(range(onp.ndim(_Value(x)))))])
  ns.expand_dims = lambda x, axis: _Record('expand_dims', [x, axis])
  ns.sum = lambda x, axis=None, keepdims=False: _Record(
      'sum', [x, axis, keepdims])
  ns.prod = lambda x, axis=None, keepdims=False: _Record(
      'prod', [x, axis, keepdims])
  ns.min = lambda x, axis=None, initial=None, keepdims=False: _Record(
      'min', [x, axis, keepdims, initial])
  ns.max = lambda x, axis=None, initial=None, keepdims=False: _Record(
      'max', [x, axis, keepdims, initial])
  ns.any = lambda x, axis=None: _Record('any', [x, axis])
  ns.concatenate = lambda parts, axis=0: _Record(
      'concatenate', [axis] + list(parts))
  ns.lexsort = lambda keys, axis=-1: _Record(
      'lexsort', [axis] + list(keys))
  ns.sort = lambda x, axis=-1: _Record('sort', [x, axis])
  ns.take_along_axis = lambda a, index, axis: _Record(
      'take_along_axis', [a, index, axis])
  return ns


numpy = _MakeNumpy()


###############################################################################
# value_and_grad, scan, jit.


def _TreeMap(f, tree):
  if isinstance(tree, dict):
    return {k: _TreeMap(f, v) for k, v in tree.items()}
  if isinstance(tree, (list, tuple)):
    return type(tree)(_TreeMap(f, v) for v in tree)
  return f(tree)


def _TreeLeaves(tree, out):
  """Leaves in the same order as _TreeMap visits them."""
  if isinstance(tree, dict):
    for k in tree:
      _TreeLeaves(tree[k], out)
  elif isinstance(tree, (list, tuple)):
    for v in tree:
      _TreeLeaves(v, out)
  else:
    out.append(tree)
  return out


def _Backward(tape, output_node, leaf_nodes):
  """Accumulates cotangents from the output down to the leaves.

  Gradient computations go through public operations and extend the
  same tape; iteration covers only the forward segment."""
  cotangent = {id(output_node): onp.ones(onp.shape(output_node.value))}
  forward = tape[:output_node.index + 1]
  for node in reversed(forward):
    g = cotangent.get(id(node))
    if g is None or node.op in ('leaf', 'const'):
      continue
    rule = _GRAD.get(node.op)
    if rule is None:
      continue  # Non-differentiable op: nothing flows further.
    argument_grads = rule(node, g)
    for arg, arg_grad in zip(node.args, argument_grads):
      if arg_grad is None or not _Recorded(arg):
        continue
      known = cotangent.get(id(arg))
      cotangent[id(arg)] = (arg_grad if known is None
                            else known + arg_grad)
  return cotangent


def value_and_grad(function):
  """Reverse-mode gradient over the first argument (a pytree)."""
  def Wrapped(params, *rest):
    ambient = _Tape()
    tape = ambient if ambient is not None else []
    _STATE.tape = tape
    try:
      leaf_nodes = []

      def BoxLeaf(x):
        if isinstance(x, Tensor) and x.node.recorded:
          leaf_nodes.append(x.node)
          return x
        node = Node('leaf', [], onp.asarray(_Value(x)), len(tape))
        tape.append(node)
        leaf_nodes.append(node)
        return Tensor(node)

      boxed_params = _TreeMap(BoxLeaf, params)
      output = function(boxed_params, *rest)
      if not (isinstance(output, Tensor) and output.node.recorded):
        raise LogixError('Differentiated function must return a value '
                         'depending on the parameters.')
      cotangent = _Backward(tape, output.node, leaf_nodes)

      position = [0]

      def GradLeaf(unused_leaf):
        node = leaf_nodes[position[0]]
        position[0] += 1
        g = cotangent.get(id(node))
        if g is None:
          return _Constant(onp.zeros(onp.shape(node.value)))
        return g if isinstance(g, Tensor) else _Constant(g)

      grads = _TreeMap(GradLeaf, params)
      if ambient is None:
        return output.node.value, _TreeMap(_Value, grads)
      return output, grads
    finally:
      _STATE.tape = ambient
  Wrapped._logix_traceable = True
  return Wrapped


class _Lax(object):

  @staticmethod
  def scan(f, init, xs, length=None):
    if xs is not None:
      raise LogixError('logix scan supports only xs=None.')
    carry = init
    for _ in range(length):
      carry, unused_y = f(carry, None)
    return carry, None


lax = _Lax()


def jit(function):
  """Trace once, serialize the tape into straight-line numpy, reuse.

  The graphs of the neural fragment are static, so one trace per
  argument signature is exact. LOGIX_JIT=0 disables compilation and
  calls the function as is: the interpreted reference mode."""
  if os.environ.get('LOGIX_JIT', '1') == '0':
    return function
  cache = {}

  def Wrapped(*args):
    leaves = [onp.asarray(_Value(x)) for x in _TreeLeaves(args, [])]
    signature = tuple((x.shape, x.dtype.str) for x in leaves)
    if signature not in cache:
      cache[signature] = _Compile(function, args)
    return cache[signature](leaves)
  return Wrapped


def _Compile(function, args):
  """Runs one traced call and emits the tape as a python function."""
  tape = []
  _STATE.tape = tape
  try:
    leaf_positions = {}

    def BoxLeaf(x):
      node = Node('leaf', [], onp.asarray(_Value(x)), len(tape))
      tape.append(node)
      leaf_positions[id(node)] = len(leaf_positions)
      return Tensor(node)

    boxed_args = _TreeMap(BoxLeaf, args)
    output = function(*boxed_args)
  finally:
    _STATE.tape = None

  constants = []

  def ConstRef(value):
    constants.append(value)
    return '_c[%d]' % (len(constants) - 1)

  names = {}

  def Ref(arg):
    if isinstance(arg, Node):
      if id(arg) in names:
        return names[id(arg)]
      return ConstRef(arg.value)  # A free node: a constant subgraph.
    if isinstance(arg, float) and not onp.isfinite(arg):
      return "float('%s')" % repr(float(arg))
    if isinstance(arg, float):
      return repr(float(arg))  # np.float64 subclasses float; clean repr.
    if isinstance(arg, (bool, int, str)) or arg is None:
      return repr(arg)
    if isinstance(arg, tuple) and all(
        isinstance(i, (bool, int)) for i in arg):
      return repr(arg)
    return ConstRef(arg)

  for node in tape:
    if node.op == 'leaf':
      names[id(node)] = '_a[%d]' % leaf_positions[id(node)]

  expression_emitters = {
      'add': '({0} + {1})', 'sub': '({0} - {1})', 'mul': '({0} * {1})',
      'div': '({0} / {1})', 'pow': 'onp.power({0}, {1})',
      'mod': 'onp.mod({0}, {1})', 'neg': '(-{0})',
      'eq': 'onp.equal({0}, {1})', 'ne': 'onp.not_equal({0}, {1})',
      'lt': '({0} < {1})', 'le': '({0} <= {1})',
      'gt': '({0} > {1})', 'ge': '({0} >= {1})',
      'sum': 'onp.sum({0}, axis={1}, keepdims={2})',
      'prod': 'onp.prod({0}, axis={1}, keepdims={2})',
      'any': 'onp.any({0}, axis={1})',
      'gather': '{0}[{1}]',
      'where': 'onp.where({0}, {1}, {2})',
      'broadcast_to': 'onp.broadcast_to({0}, {1})',
      'reshape': 'onp.reshape({0}, {1})',
      'transpose': 'onp.transpose({0}, {1})',
      'expand_dims': 'onp.expand_dims({0}, {1})',
      'astype': 'onp.asarray({0}).astype({1})',
      'take_along_axis': 'onp.take_along_axis({0}, {1}, axis={2})',
  }
  plain_calls = {'abs', 'exp', 'log', 'sqrt', 'sin', 'cos', 'floor',
                 'logical_and', 'logical_or', 'logical_not',
                 'minimum', 'maximum'}
  scatter_calls = {'scatter_add': 'onp.add.at',
                   'scatter_min': 'onp.minimum.at',
                   'scatter_max': 'onp.maximum.at'}

  lines = []
  for node in tape:
    if node.op in ('leaf', 'const'):
      continue
    name = '_v%d' % node.index
    refs = [Ref(a) for a in node.args]
    if node.op in expression_emitters:
      lines.append('%s = %s' % (
          name, expression_emitters[node.op].format(*refs)))
    elif node.op in plain_calls:
      lines.append('%s = onp.%s(%s)' % (name, node.op, ', '.join(refs)))
    elif node.op == 'einsum':
      lines.append('%s = onp.einsum(%s)' % (name, ', '.join(refs)))
    elif node.op == 'concatenate':
      lines.append('%s = onp.concatenate([%s], axis=%s)' % (
          name, ', '.join(refs[1:]), refs[0]))
    elif node.op == 'lexsort':
      lines.append('%s = onp.lexsort((%s,), axis=%s)' % (
          name, ', '.join(refs[1:]), refs[0]))
    elif node.op == 'sort':
      lines.append('%s = onp.sort(%s, axis=%s)' % (
          name, refs[0], refs[1]))
    elif node.op in ('min', 'max'):
      x, axis, keepdims, initial = refs
      suffix = (', initial=%s' % initial
                if node.args[3] is not None else '')
      lines.append('%s = onp.%s(%s, axis=%s, keepdims=%s%s)' % (
          name, node.op, x, axis, keepdims, suffix))
    elif node.op in scatter_calls:
      lines.append('%s = onp.array(%s)' % (name, refs[0]))
      lines.append('%s(%s, %s, %s)' % (scatter_calls[node.op],
                                       name, refs[1], refs[2]))
    elif node.op == 'scatter_set':
      lines.append('%s = onp.array(%s)' % (name, refs[0]))
      lines.append('%s[%s] = %s' % (name, refs[1], refs[2]))
    else:
      raise LogixError('No emitter for op %s.' % node.op)
    names[id(node)] = name

  output_refs = []
  structure = _TreeMap(
      lambda x: output_refs.append(
          Ref(x.node) if isinstance(x, Tensor) else ConstRef(x)) or (
              len(output_refs) - 1),
      output)
  lines.append('return [%s]' % ', '.join(output_refs))

  source = (
      'def _compiled(_a):\n'
      "  with onp.errstate(invalid='ignore', divide='ignore', "
      "over='ignore'):\n"
      '    ' + '\n    '.join(lines) + '\n')
  dump = os.environ.get('LOGIX_DUMP_SOURCE')
  if dump:
    with open(dump, 'w') as f:
      f.write(source)
  scope = {'onp': onp, '_c': constants}
  exec(source, scope)  # Code generated just above from the tape.
  compiled = scope['_compiled']

  def Run(leaves):
    flat = compiled(leaves)
    return _TreeMap(lambda index: flat[index], structure)

  Run.source = source
  return Run


###############################################################################
# jax-module compatibility shims.


class _Config(object):

  def update(self, unused_key, unused_value):
    pass  # Numpy already defaults to float64; nothing to configure.


config = _Config()


@contextlib.contextmanager
def ensure_compile_time_eval():
  yield
