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

"""Renders an HTML report of an MNIST run.

Reads /tmp/logica_mnist/mnist.duckdb — the pixels, the labels and the
predictions that the Logica program stored — and writes an HTML gallery
of recognized digits: one correct example per digit and the first
misread images.

Arguments (all optional):
  render_report.py [prediction_table] [report_name] [baseline_table]

With a baseline table the report also shows the digits this model fixed:
images the baseline misread and this model reads correctly.
"""

import collections
import os
import sys

import duckdb

DATA_DIRECTORY = '/tmp/logica_mnist'
DATABASE = os.path.join(DATA_DIRECTORY, 'mnist.duckdb')

ERRORS_TO_SHOW = 12


def DigitSvg(pixels, size=84):
  """A 28x28 digit as an SVG image; pixels is {pixel_id: intensity}."""
  cell = size / 28.0
  rectangles = []
  for pixel, intensity in sorted(pixels.items()):
    row, column = divmod(pixel, 28)
    shade = 255 - int(round(255 * intensity))
    rectangles.append(
        '<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" '
        'fill="rgb(%d,%d,%d)"/>' %
        (column * cell, row * cell, cell + 0.5, cell + 0.5,
         shade, shade, shade))
  return ('<svg width="%d" height="%d" '
          'style="background: white">%s</svg>' %
          (size, size, ''.join(rectangles)))


def Card(svg, caption, good):
  color = '#2a7' if good else '#c33'
  return ('<div style="display: inline-block; margin: 6px; padding: 6px;'
          ' border: 2px solid %s; border-radius: 8px;'
          ' text-align: center; font-family: monospace;">'
          '%s<br>%s</div>' % (color, svg, caption))


def main():
  prediction_table = sys.argv[1] if len(sys.argv) > 1 else 'prediction'
  report_name = sys.argv[2] if len(sys.argv) > 2 else 'report.html'
  baseline_table = sys.argv[3] if len(sys.argv) > 3 else None
  report_path = os.path.join(DATA_DIRECTORY, report_name)

  connection = duckdb.connect(DATABASE, read_only=True)
  labels = dict(connection.execute(
      'SELECT col0, col1 FROM test_label').fetchall())
  predictions = dict(connection.execute(
      'SELECT col0, col1 FROM %s' % prediction_table).fetchall())
  baseline = {}
  if baseline_table:
    try:
      baseline = dict(connection.execute(
          'SELECT col0, col1 FROM %s' % baseline_table).fetchall())
    except duckdb.CatalogException:
      print('No %s table: run the baseline example to compare.' %
            baseline_table)

  correct = sum(1 for e in labels if predictions.get(e) == labels[e])
  accuracy = 100.0 * correct / len(labels)

  # One correctly recognized example per digit, and the first errors.
  correct_example_of = {}
  errors = []
  for e in sorted(labels):
    actual, predicted = labels[e], predictions.get(e)
    if predicted == actual:
      correct_example_of.setdefault(actual, e)
    elif len(errors) < ERRORS_TO_SHOW:
      errors.append(e)

  # Digits the baseline misread and this model reads correctly.
  fixed = [e for e in sorted(labels)
           if baseline and baseline.get(e) != labels[e]
           and predictions.get(e) == labels[e]]
  fixed_shown = fixed[:ERRORS_TO_SHOW]

  shown = sorted(correct_example_of.values()) + errors + fixed_shown
  pixels_of = collections.defaultdict(dict)
  rows = connection.execute(
      'SELECT col0, col1, logica_value FROM test_pixel '
      'WHERE col0 IN (%s)' % ', '.join(map(str, shown))).fetchall()
  for e, pixel, intensity in rows:
    pixels_of[e][pixel] = intensity
  connection.close()

  cards_correct = [
      Card(DigitSvg(pixels_of[e]), 'read as %d' % labels[e], good=True)
      for e in sorted(correct_example_of.values())]
  cards_errors = [
      Card(DigitSvg(pixels_of[e]),
           'was %d, read as %d' % (labels[e], predictions[e]), good=False)
      for e in errors]
  cards_fixed = [
      Card(DigitSvg(pixels_of[e]),
           '%d; baseline read %d' % (labels[e], baseline[e]), good=True)
      for e in fixed_shown]
  fixed_section = ''
  if baseline:
    broken = sum(1 for e in labels
                 if baseline.get(e) == labels[e]
                 and predictions.get(e) != labels[e])
    fixed_section = (
        '<h2>Fixed relative to the baseline</h2>'
        '<p>%d images the baseline misread are now correct '
        '(and %d correct ones broke).</p>%s' %
        (len(fixed), broken, ''.join(cards_fixed)))

  html = '''<!doctype html>
<html><head><meta charset="utf-8"><title>MNIST in Logica</title></head>
<body style="font-family: sans-serif; max-width: 60em; margin: 2em auto;">
<h1>MNIST digit recognition in Logica</h1>
<p>A one-hidden-layer perceptron written as Logica rules and trained by
<code>@NeuralTarget</code> on 60000 images. Accuracy on the 10000 test
images: <b>%.2f%%</b> (%d of %d).</p>
<h2>Recognized correctly</h2>
%s
<h2>Misread</h2>
%s
%s
</body></html>''' % (accuracy, correct, len(labels),
                     ''.join(cards_correct), ''.join(cards_errors),
                     fixed_section)

  with open(report_path, 'w') as f:
    f.write(html)
  print('Report: %s' % report_path)


if __name__ == '__main__':
  main()
