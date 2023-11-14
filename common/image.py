#!/usr/bin/python
#
# Copyright 2023 Google LLC
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

"""Utility for drawing images."""

import numpy
from matplotlib import pyplot
from matplotlib import animation

import IPython


def Animate(spacetime,
            column_x='col0',
            column_y='col1',
            column_t='col2',
            column_v='logica_value',
            field_width=None,
            field_height=None,
            cmap='hot',
            vmin=0,
            vmax=None,
            shadow_factor=0.5,
            min_shadow=0.1,
            gif_file='animation.gif',
            should_display=True,
            fps=10):
  """Animating a dataframe."""
  fig, ax = pyplot.subplots()
  if field_width is None:
    field_width = max(spacetime[column_x]) + 1
  if field_height is None:
    field_height = max(spacetime[column_y]) + 1  
  field_shape = (field_width, field_height)

  if column_v is None:
    column_v = '*magical_indicator_column*'
    spacetime[column_v] = 1
  if column_v == 'logica_value' and 'logica_value' not in spacetime:
    spacetime['logica_value'] = 1

  if vmin is None:
    vmin = min(spacetime[column_v])
  if vmax is None:
    vmax = max(spacetime[column_v])
  r = numpy.zeros(field_shape)
  img = pyplot.imshow(r.T, cmap=cmap, vmin=vmin, vmax=vmax)

  def Update(frame):
    r = numpy.zeros(field_shape)
    decay = 1
    i = 0
    while decay > min_shadow:
      m = numpy.zeros(field_shape)
      df = spacetime[spacetime[column_t] == (frame - i)]
      m[df[column_x], df[column_y]] = df[column_v] * decay
      r = numpy.maximum(r, m)
      decay *= shadow_factor
      i += 1
    img.set_data(r.T)
  ani = animation.FuncAnimation(
    fig, Update, frames=range(max(spacetime[column_t])))
  ani.save(gif_file, writer='pillow', fps=fps)
  if should_display:
    IPython.display.display(IPython.display.Image(filename=gif_file))
  pyplot.close(fig)

def ShowImage(img,
              column_x='col0',
              column_y='col1',
              column_v='logica_value',
              field_width=None,
              field_height=None,
              cmap='hot',
              vmin=0,
              vmax=None):
  """Showing dataframe as an image."""
  pyplot.figure()
  if column_v is None or (column_v == 'logica_value' and
                          column_v not in img):
    if column_v is None:
      column_v = '*magical_indicator_column*'
    img[column_v] = numpy.zeros(len(img)) + 1
  if field_width is None:
    field_width = max(img[column_x]) + 1
  if field_height is None:
    field_height = max(img[column_y]) + 1  
  field_shape = (field_width, field_height)

  if vmin is None:
    vmin = min(img[column_v])
  if vmax is None:
    vmax = max(img[column_v])
  r = numpy.zeros(field_shape)
  r[img[column_x], img[column_y]] = img[column_v]
  pyplot.imshow(r.T, cmap=cmap, vmin=vmin, vmax=vmax)

