"""Concertina: small Python Workflow execution handler."""

import datetime

try:
  import graphviz
  from IPython.display import display
  from IPython.display import update_display
except:
  print('Could not import CoLab tools in Concertina.')

if '.' not in __package__:
  from common import graph_art
else:
  from ..common import graph_art

class ConcertinaQueryEngine(object):
  def __init__(self, final_predicates, sql_runner,
               print_running_predicate=True):
    self.final_predicates = final_predicates
    self.final_result = {}
    self.sql_runner = sql_runner
    self.print_running_predicate = print_running_predicate

  def Run(self, action):
    assert action['launcher'] in ('query', 'none')
    if action['launcher'] == 'query':
      predicate = action['predicate']
      if self.print_running_predicate:
        print('Running predicate:', predicate, end='')
      start = datetime.datetime.now()
      result = self.sql_runner(action['sql'], action['engine'],
                               is_final=(predicate in self.final_predicates))
      end = datetime.datetime.now()
      if self.print_running_predicate:
        print(' (%d seconds)' % (end - start).seconds)
      if predicate in self.final_predicates:
        self.final_result[predicate] = result


class ConcertinaDryRunEngine(object):
  def Run(self, action):
    print(action)


class Concertina(object):
  DISPLAY_COUNT = 0

  @classmethod
  def GetDisplayId(cls):
    cls.DISPLAY_COUNT = cls.DISPLAY_COUNT + 1
    return 'Concertina_%d' % cls.DISPLAY_COUNT

  def SortActions(self):
    actions_to_assign = {a['name'] for a in self.config}
    complete = set()
    result = []
    while actions_to_assign:
      remains = len(actions_to_assign)
      for a in list(actions_to_assign):
        if complete >= set(self.action[a]["requires"]):
          result.append(a)
          complete |= {a}
          actions_to_assign -= {a}
      if len(actions_to_assign) == remains:
        assert False, "Could not schedule: %s" % self.config
    return result
      
  def __init__(self, config, engine, display_mode='colab'):
    self.config = config
    self.action = {a["name"]: a for a in self.config}
    self.actions_to_run = self.SortActions()
    self.engine = engine
    assert len(self.action) == len(self.config)
    self.all_actions = {a["name"] for a in self.config}
    self.complete_actions = set()
    self.running_actions = set()
    assert display_mode in ('colab', 'terminal'), (
      'Unrecognized display mode: %s' % display_mode)
    self.display_mode = display_mode
    self.display_id = self.GetDisplayId()
    self.Display()

  def RunOneAction(self):
    self.UpdateDisplay()
    one_action = self.actions_to_run[0]
    del self.actions_to_run[0]
    self.running_actions |= {one_action}
    self.UpdateDisplay()
    self.engine.Run(self.action[one_action].get('action', {}))
    self.running_actions -= {one_action}
    self.complete_actions |= {one_action}
    self.UpdateDisplay()

  def Run(self):
    while self.actions_to_run:
      self.RunOneAction()

  def ActionColor(self, a):
    if self.action[a].get('type') == 'data':
      return 'lightskyblue1'
    if a in self.complete_actions:
      return 'darkolivegreen1'
    if a in self.running_actions:
      return 'gold'
    return 'gray'

  def ActionShape(self, a):
    if 'type' in self.action[a]:
      action_type = self.action[a]['type']
      if action_type == 'data':
        return 'cylinder'
      if action_type == 'final':
        return 'diamond'
    return 'box'

  def AsGraphViz(self):
    g = graphviz.Digraph('Concertina')
    for a in self.all_actions:
      color = self.ActionColor(a)
      shape = self.ActionShape(a)
      styles = ['filled']

      g.node(a, shape=shape, fillcolor=color, style='filled,rounded', color='gray34')
      for prerequisite in self.action[a]['requires']:
        g.edge(prerequisite, a)

    return g

  def AsTextPicture(self, updating):
    def AsArtGraph():
      nodes, edges = self.AsNodesAndEdges()
      return graph_art.Graph(nodes, edges)
    return AsArtGraph().GetPicture(updating=updating)

  def AsNodesAndEdges(self):
    """Nodes and edges to display in terminal."""
    def ColoredNode(node):
      if node in self.running_actions:
        return '\033[1m\033[93m' + node + '\033[0m'
      else:
        return node
    nodes = []
    edges = []
    for a in self.all_actions:
      a_node = ColoredNode(a)
      nodes.append(a_node)
      for prerequisite in self.action[a]['requires']:
        prerequisite_node = ColoredNode(prerequisite)
        edges.append([prerequisite_node, a_node])
    return nodes, edges

  def Display(self):
    if self.display_mode == 'colab':
      display(self.AsGraphViz(), display_id=self.display_id)
    elif self.display_mode == 'terminal':
      print(self.AsTextPicture(updating=False))
    else:
      assert 'Unexpected mode:', self.display_mode

  def UpdateDisplay(self):
    if self.display_mode == 'colab':
      update_display(self.AsGraphViz(), display_id=self.display_id)
    elif self.display_mode == 'terminal':
      print(self.AsTextPicture(updating=True))
    else:
      assert 'Unexpected mode:', self.display_mode

def RenamePredicate(table_to_export_map, dependency_edges,
                    data_dependency_edges, from_name, to_name):
  new_table_to_export_map = {}
  new_dependency_edges = set()
  new_data_dependency_edges = set()
  for k, v in table_to_export_map.items():
    if k == from_name:
      new_table_to_export_map[to_name] = v
    else:
      new_table_to_export_map[k] = v
  for a, b in dependency_edges:
    if a == from_name:
      a = to_name
    if b == from_name:
      b = to_name
    new_dependency_edges.add((a, b))
  for a, b in data_dependency_edges:
    if a == from_name:
      a = to_name
    if b == from_name:
      b = to_name
    new_data_dependency_edges.add((a, b))
  return new_table_to_export_map, new_dependency_edges, new_data_dependency_edges


def ExecuteLogicaProgram(logica_executions, sql_runner, sql_engine,
                         display_mode='colab'):
  def ConcertinaConfig(table_to_export_map, dependency_edges,
                       data_dependency_edges, final_predicates):
    depends_on = {}
    for source, target in dependency_edges | data_dependency_edges:
      depends_on[target] = depends_on.get(target, set()) | {source}

    data = {d for d, _ in data_dependency_edges}
    data |= {d for d, _ in dependency_edges if d not in table_to_export_map}
    
    result = []
    for d in data:
      result.append({
          'name': d,
          'type': 'data',
          'requires': [],
          'action': {
              'predicate': d,
              'launcher': 'none'
          }
      })
    for t, sql in table_to_export_map.items():
      result.append({
          'name': t,
          'type': ('final' if t in final_predicates else 'intermediate'),
          'requires': list(depends_on.get(t, set())),
          'action': {
              'predicate': t,
              'launcher': 'query',
              'engine': sql_engine,
              'sql': sql
          }
      })
    return result

  table_to_export_map = {}
  dependency_edges = set()
  data_dependency_edges = set()
  final_predicates = {e.main_predicate for e in logica_executions}
  
  for e in logica_executions:
    p_table_to_export_map, p_dependency_edges, p_data_dependency_edges = (
        e.table_to_export_map, e.dependency_edges, e.data_dependency_edges
    )
    for p in final_predicates:
      if e.main_predicate != p and p in e.table_to_export_map:
        p_table_to_export_map, p_dependency_edges, p_data_dependency_edges = (
          RenamePredicate(
            p_table_to_export_map, p_dependency_edges, p_data_dependency_edges,
            p, '⤓' + p))

    for k, v in p_table_to_export_map.items():
      table_to_export_map[k] = e.PredicateSpecificPreamble(e.main_predicate) + v

    for a, b in p_dependency_edges:
      dependency_edges.add((a, b))
    for a, b in p_data_dependency_edges:
      data_dependency_edges.add((a, b))

  config = ConcertinaConfig(table_to_export_map,
                            dependency_edges,
                            data_dependency_edges,
                            final_predicates)
 
  engine = ConcertinaQueryEngine(
      final_predicates=final_predicates, sql_runner=sql_runner,
      print_running_predicate=(display_mode != 'terminal'))

  preambles = set(e.preamble for e in logica_executions)
  assert len(preambles) == 1, 'Inconsistent preambles: %s' % preambles
  [preamble] = list(preambles)
  if preamble:
    sql_runner(preamble, sql_engine, is_final=False)

  concertina = Concertina(config, engine, display_mode=display_mode)
  concertina.Run()
  return engine.final_result
