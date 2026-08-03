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

"""Packs the downloaded MNIST files into a DuckDB database.

Reads the four IDX files from /tmp/logica_mnist and writes
/tmp/logica_mnist/mnist.duckdb with tables train_pixel, train_label,
test_pixel and test_label. Pixels are normalized to [0, 1]; only
nonzero pixels are stored — an absent row is an absent pixel.
"""

import gzip
import os
import struct

import duckdb
import numpy
import pandas

DATA_DIRECTORY = '/tmp/logica_mnist'
DATABASE = os.path.join(DATA_DIRECTORY, 'mnist.duckdb')


def ReadImages(filename):
  with gzip.open(os.path.join(DATA_DIRECTORY, filename)) as f:
    unused_magic, n, rows, columns = struct.unpack('>IIII', f.read(16))
    return numpy.frombuffer(f.read(), dtype=numpy.uint8).reshape(
        n, rows * columns)


def ReadLabels(filename):
  with gzip.open(os.path.join(DATA_DIRECTORY, filename)) as f:
    unused_magic, n = struct.unpack('>II', f.read(8))
    return numpy.frombuffer(f.read(), dtype=numpy.uint8)


def WritePixels(connection, table, images):
  examples, pixels = numpy.nonzero(images)
  frame = pandas.DataFrame({
      'col0': examples.astype(numpy.int64),
      'col1': pixels.astype(numpy.int64),
      'logica_value': images[examples, pixels].astype(numpy.float64) / 255.0,
  })
  connection.register('frame', frame)
  connection.execute('CREATE TABLE %s AS SELECT * FROM frame' % table)
  connection.unregister('frame')
  print('%s: %d nonzero pixels' % (table, len(frame)))


def WriteLabels(connection, table, labels):
  frame = pandas.DataFrame({
      'col0': numpy.arange(len(labels), dtype=numpy.int64),
      'col1': labels.astype(numpy.int64),
  })
  connection.register('frame', frame)
  connection.execute('CREATE TABLE %s AS SELECT * FROM frame' % table)
  connection.unregister('frame')
  print('%s: %d labels' % (table, len(frame)))


def main():
  if os.path.exists(DATABASE):
    print('%s already exists.' % DATABASE)
    return
  connection = duckdb.connect(DATABASE)
  WritePixels(connection, 'train_pixel',
              ReadImages('train-images-idx3-ubyte.gz'))
  WriteLabels(connection, 'train_label',
              ReadLabels('train-labels-idx1-ubyte.gz'))
  WritePixels(connection, 'test_pixel',
              ReadImages('t10k-images-idx3-ubyte.gz'))
  WriteLabels(connection, 'test_label',
              ReadLabels('t10k-labels-idx1-ubyte.gz'))
  connection.close()
  print('%s is ready.' % DATABASE)


if __name__ == '__main__':
  main()
