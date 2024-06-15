#!/usr/bin/python
#
# Copyright 2020 Google LLC
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

"""Basic VisJS graph visualization wrapper."""

from IPython.display import display, HTML
import urllib
import json
import numpy

visjs = urllib.request.urlopen('https://raw.githubusercontent.com/EvgSkv/vis/master/dist/vis-network.min.js').read()
css = urllib.request.urlopen('https://raw.githubusercontent.com/EvgSkv/vis/master/dist/vis-network.min.css').read()

RENDERED_GRAPHS = 0

def GraphHtml(nodes, edges, options, width, height):
  html_colab = r"""
  <script type="text/javascript">
  %(visjs)s
  </script>
  <style>
  %(css)s
  </style>
  <style type="text/css">
  #graph_%(idx)s {
    width: %(width)spx;
    height: %(height)spx;
    border: 1px solid lightgray;
  }
  </style>
  <div id="graph_%(idx)s"></div>

  <script type="text/javascript">
    // Nodes array.
    var nodes = new vis.DataSet(%(nodes)s);

    // Edges array.
    var edges = new vis.DataSet(%(edges)s);

    // Network.
    var container = document.getElementById('graph_%(idx)s');
    var data = {
      nodes: nodes,
      edges: edges
    };
    var options = %(options)s;
    var network = new vis.Network(container, data, options);
  </script>
  """

  html_jupyter = r"""
  <style>
  %(css)s
  </style>
  <style type="text/css">
  #graph_%(idx)s {
    width: %(width)spx;
    height: %(height)spx;
    border: 1px solid lightgray;
  }
  </style>
  <div id="graph_%(idx)s"></div>

  <script type="text/javascript">
    require(['https://evgskv.github.io/vis/dist/vis.js'], function(vis) {
      // Nodes array.
      var nodes = new vis.DataSet(%(nodes)s);

      // Edges array.
      var edges = new vis.DataSet(%(edges)s);

      // Network.
      var container = document.getElementById('graph_%(idx)s');
      var data = {
        nodes: nodes,
        edges: edges
      };
      var options = %(options)s;
      var network = new vis.Network(container, data, options);
    });
  </script>
  """
  if 'google.colab' in str(get_ipython()):
    html = html_colab
  else:
    html = html_jupyter
  global RENDERED_GRAPHS
  idx = RENDERED_GRAPHS
  RENDERED_GRAPHS = RENDERED_GRAPHS + 1
  result = html % dict(visjs=visjs.decode(), css=css.decode(),
                       nodes=json.dumps(nodes),
                       edges=json.dumps(edges),
                       options=json.dumps(options),
                       height=height,
                       width=width,
                       idx=idx)
  return result

def DisplayGraph(nodes, edges, options=None, width=640, height=480):
  options = options or {}
  html = GraphHtml(nodes, edges, options, width, height)
  display(HTML(html))

def MakeNode(n, node_colors):
  node_colors = node_colors or {}
  if n in node_colors:
    return {'id': n, 'label': str(n), 'color': node_colors[n]}
  return {'id': n, 'label': str(n)}

def MakeEdge(e, extra=None):
  extra = extra or {}
  if len(e) == 2:
    r = {"from": e[0], "to": e[1]}
  elif len(e) == 3:
    r = {"from": e[0], "to": e[1], "color": {"color": e[2]}}
  else:
    assert 'Bad edge: ' + str(e)
  r.update(**extra)
  return r

def SimpleGraphFromList(edges, options=None, node_colors=None):
  if node_colors is not None:
    node_colors = dict(zip(map(str, node_colors['col0']),
                           node_colors['logica_value']))
  nodes = list({n for e in edges for n in e[:2]})
  nodes_json = [MakeNode(n, node_colors) for n in nodes]
  edges_json = [MakeEdge(e) for e in edges]
  DisplayGraph(nodes_json, edges_json, options=options)

def GraphFromListOfEdgeDicts(edges, node_colors, options):
  if node_colors is not None:
    node_colors = dict(zip(map(str, node_colors['col0']),
                           node_colors['logica_value']))
  nodes = list(set(n for e in edges for n in {e['from'], e['to']}))
  nodes_json = [MakeNode(n, node_colors) for n in nodes]
  extra_args = {}
  if options:
    if 'width' in options:
      extra_args['width'] = options['width']
    if 'height' in options:
      extra_args['height'] = options['height']
  DisplayGraph(nodes_json, edges, options=options, **extra_args)

def SimpleGraph(p, source='col0', target='col1', options=None,
                node_colors=None, edge_color_column=None,
                edge_width_column=None,
                extra_edges_columns=None):
  edges = []
  extra_edges_columns = extra_edges_columns or []
  for _, row in p.iterrows():
    edge = {'from': str(row[source]), 'to': str(row[target])}
    if edge_color_column:
      edge['color'] = {'color': row[edge_color_column]}
    if edge_width_column:
      edge['width'] = float(row[edge_width_column])
    for c in extra_edges_columns:
      edge[c] = row[c]
    edges.append(edge)
  GraphFromListOfEdgeDicts(edges, node_colors, options=options)

def DirectedGraphFromList(edges, options=None, node_colors=None):
  if node_colors is not None:
    node_colors = dict(zip(map(str, node_colors['col0']),
                           node_colors['logica_value']))
  nodes = list({n for e in edges for n in e[:2]})
  nodes_json = [MakeNode(n, node_colors) for n in nodes]
  edges_json = [MakeEdge(e, {"arrows": "to"})
                for e in edges]
  DisplayGraph(nodes_json, edges_json, options=options)

def DirectedGraph(p, source='col0', target='col1', options=None,
                  node_colors=None, edge_color_column=None, edge_width_column=None):
  edges = []
  for _, row in p.iterrows():
    edge = {'from': str(row[source]), 'to': str(row[target])}
    if edge_color_column:
      edge['color'] = {'color': row[edge_color_column]}
    if edge_width_column:
      edge['width'] = float(row[edge_width_column])
    edge['arrows'] = 'to'
    edges.append(edge)
  GraphFromListOfEdgeDicts(edges, node_colors, options=options)

def Graph(nodes, edges, options=None, width=640, height=480):
  nodes_list = [dict(n) for _, n in nodes.iterrows()]
  edges_list = [dict(e) for _, e in edges.iterrows()]
  def Convert(l):
    for e in l:
      for k in list(e):
        if isinstance(e[k], numpy.int64):
          e[k] = int(e[k])
        if k == 'source':
          e['from'] = e[k]
        if k == 'target':
          e['to'] = e[k]
        if k == 'class':
          e['group'] = e[k]
  Convert(nodes_list)
  Convert(edges_list)
  options_obj = {} if options is None else dict(options.iloc[0])
  Convert([options_obj])
  DisplayGraph(nodes_list, edges_list, options_obj, width, height)


def HierarchicalOptions():
  return {'layout': {'hierarchical': {'direction': 'UD',
                                      'sortMethod': 'directed'}}}