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

# Library to draw ASCII directed acyclic graph.


class Graph(object):
  def __init__(self, nodes, edges):
    self.nodes = nodes
    self.edges = edges
    self.dependencies = {n: [] for n in nodes}
    self.dependants = {n: [] for n in nodes}
    for a, b in edges:
      self.dependencies[b] += [a]
      self.dependants[a] += [b]
    self.SortNodes()
    self.necessary_dependants = {n: set() for n in nodes}
    self.necessary_dependants = {n: [] for n in nodes}
    self.ComputeNecessaryDependencies()
  
  def ComputeNecessaryDependencies(self):
    nodes = self.nodes
    implied_dependencies = {n: set() for n in nodes}
    necessary_dependencies = {n: set() for n in nodes}
    for node in self.nodes:
      for n in self.dependencies[node]:
        implied_dependencies[node] |= implied_dependencies[n]
      necessary_dependencies[node] = set(
        set(self.dependencies[node]) - implied_dependencies[node])
      implied_dependencies[node] |= set(self.dependencies[node])
    self.necessary_dependencies = necessary_dependencies
    for n, deps in self.necessary_dependencies.items():
      for d in deps:
        self.necessary_dependants[d] += [n]

  def SortNodes(self):
    placed = set()
    result = []
    while len(placed) < len(self.nodes):
      for node in self.nodes:
        if node in placed:
          continue
        for d in self.dependencies[node]:
          if d not in placed:
            break
        else:
          result.append(node)
          placed |= {node}
    self.nodes = result

  def SimulateDelivery(self):
    all_tracks = set(range(len(self.edges)))
    tracks_image = []
    carts = {}
    busy_tracks = set()
    get_track = lambda: min(all_tracks - busy_tracks)
    for node in self.nodes:
      new_tracks = set()
      done_tracks = set()
      num_used_tracks = lambda: (
        0 if not busy_tracks else max(busy_tracks) + 1)
      dependants = set(self.necessary_dependants[node])

      # Adding carts towards all dependants.
      # TODO: Write this to be linear in len(self.dependants[node]).
      # We want to traverse over dependants in the order in which they occur
      # in self.nodes.
      for d in self.nodes:
        if d in dependants:
          track = get_track()
          carts[node, d] = track
          busy_tracks |= {track}
          new_tracks |= {track}

      # Retracting carts arriving from dependencies.
      plot_tracks = num_used_tracks()
      for d in self.necessary_dependencies[node]:
        track = carts[d, node]
        del carts[d, node]
        busy_tracks -= {track}
        done_tracks |= {track}

      # Drawing a row.
      row = ''
      char_space = ' '
      char_start = '╥'
      char_end = '╨'
      char_pipe = '║'
      for i in range(plot_tracks):
        if i in new_tracks:
          row += char_start
        elif i in done_tracks:
          row += char_end
        elif i in busy_tracks:
          row += char_pipe
        else:
          row += char_space

      # Appendig the row.
      tracks_image.append(row)
      tracks_image.append(''.join(
          (char_pipe if c == char_start or c == char_pipe else char_space
           for c in row)))
    width = max(map(len, tracks_image))
    tracks_image = [row + char_space * (width - len(row))
                    for row in tracks_image]
    char_field = '▚'
    field = f' {char_field}  '
    tracks_image = [
      row + field + str(self.nodes[i // 2])
      if i % 2 == 0 else row + field
      for i, row in enumerate(tracks_image)]
    # Producing a condenced 
    return tracks_image[::2]

  def GetPicture(self, updating, extra_lines=None):
    extra_lines = extra_lines or []
    picture = '\n'.join(self.SimulateDelivery() + extra_lines)
    if updating:
      prefix = '\033[F' * len(picture.split('\n'))
    else:
      prefix = ''
    return prefix + picture
 