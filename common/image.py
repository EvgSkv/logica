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
from PIL import Image
import glob


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
            fps=10,
            figsize=None,
            show_progress=True):
  """Animating a dataframe."""
  fig, ax = pyplot.subplots(figsize=figsize)
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

  num_frames = max(spacetime[column_t]) + 1
  def Update(frame):
    if show_progress:
      total = 40
      done = frame * 40 // (num_frames - 1)
      print('\rAnimating: ' + done * '▒' + (total - done) * '░',
            end='', flush=True)
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
  ani = animation.FuncAnimation(fig, Update, frames=range(num_frames))
  if show_progress:
    print('')

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

def Hexagonal(img,
              column_x='col0',
              column_y='col1',
              column_v='logica_value',
              field_width=None,
              field_height=None,
              cmap='hot',
              vmin=0,
              vmax=None,
              figsize=None):
  """Showing dataframe as an image."""
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

  hex_values = numpy.zeros(field_shape)
  hex_values[img[column_x], img[column_y]] = (
      img[column_v] - vmin) / (vmax - vmin)

  cmap = pyplot.get_cmap('hot')
  colors = cmap(hex_values)

  # Computing hexagon.
  π = 3.14159265
  angles = numpy.arange(0, 2 * π, π / 3)
  hex_delta = numpy.vstack([numpy.cos(angles), numpy.sin(angles)]).T

  def DrawOneHexagon(center, ax, color):
    hexagon = center + hex_delta
    ax.fill(hexagon[:,0], hexagon[:,1], c=color, edgecolor=color)

  fig, ax = pyplot.subplots(figsize=figsize, facecolor='black')
  ax.set_facecolor('black')

  # Get coordinates of centers.
  rows, cols = numpy.indices((field_width, field_height))
  rows = rows.flatten()
  cols = cols.flatten()
  xs = 1.5 * rows
  ys = 3 ** 0.5 * (cols + 0.5 * (rows % 2))
  centers = numpy.vstack([xs,
                          ys]).T
  
  # Draw.
  for center, color in zip(centers, colors.reshape(-1, colors.shape[-1])):
    DrawOneHexagon(center, ax, color)
  
  # Prettify.
  ax.set_aspect('equal')
  pyplot.xticks([])
  pyplot.yticks([])

def AnimateFiles(images_glob,
                 output_file,
                 duration=100,
                 and_back=False):
  imgs = [Image.open(f) for f in sorted(glob.glob(images_glob))]
  if and_back:
    imgs += reversed(imgs)
  imgs[0].save(fp=output_file, format='GIF', append_images=imgs[1:],
               save_all=True, duration=duration, loop=0)