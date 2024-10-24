"""Concertina: small Python Workflow execution handler."""

import datetime
import os

try:
  import graphviz
except:
  pass
  # This is annoying to see in terminal each time.
  # Consider adding back if lack of messaging is confusing.
  # print('Could not import graphviz tools in Concertina.')

try:
  from IPython.display import HTML
  from IPython.display import display
  from IPython.display import update_display
except:
  print('Could not import IPython in Concertina.')

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
    self.completion_time = {}

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
      self.completion_time[predicate] = int((end - start).total_seconds() * 1000)
      if self.print_running_predicate:
        print(' (%d ms)' % self.completion_time[predicate])
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
    # Sorting so that:
    # 1. Order respects dependency.
    # 2. Iterations come together.
    actions_to_assign = {a['name'] for a in self.config}
    complete = set()
    result = []
    assigning_iteration = None
    exit_for = False
    while actions_to_assign:
      remains = len(actions_to_assign)
      if assigning_iteration:
        eligible = actions_to_assign & self.iteration_actions[assigning_iteration]
      else:
        eligible = actions_to_assign
      for a in list(eligible):
        if complete >= set(self.action_requires[a]):
          result.append(a)
          if a in self.action_iteration:
            if assigning_iteration:
              assert assigning_iteration == self.action_iteration[a]
            assigning_iteration = self.action_iteration[a]
            exit_for = True
          complete |= {a}
          actions_to_assign -= {a}
          if assigning_iteration:
            if not (self.iteration_actions[assigning_iteration] & actions_to_assign):
              assigning_iteration = None
          if exit_for:
            exit_for = False
            break

      if len(actions_to_assign) == remains:
        assert False, "Could not schedule: %s from %s, \n%s" % (
          actions_to_assign,
          "\n".join(map(str, self.config)),
          self.action_requires)
    return result

  def UnderstandIterations(self):
    # Building maps from iteration to its actions and back.
    # Computing requirements ensuring that everything that iteration depends
    # on comes before it.
    self.action_iteration = {
      predicate: iteration
      for iteration in self.iterations
      for predicate in self.iterations[iteration]['predicates']
      if predicate in self.action}
    self.iteration_repetitions = {
      iteration: self.iterations[iteration]['repetitions']
      for iteration in self.iterations}
    self.action_iterations_complete = {
      p: 0
      for iteration in self.iteration_repetitions
      for p in self.iterations[iteration]['predicates']
    }
    self.iteration_actions = {
      iteration: set(self.iterations[iteration]['predicates'])
      for iteration in self.iterations
    }
    self.iteration_stop_signal = {
      iteration: self.iterations[iteration]['stop_signal']
      for iteration in self.iterations
    }
    self.half_iteration_actions = {}
    for iteration in self.iterations:
      predicates = self.iterations[iteration]['predicates']
      assert len(predicates) % 2 == 0, predicates
      self.half_iteration_actions[iteration+'_upper'] = set(predicates[:(len(predicates) // 2)])
      self.half_iteration_actions[iteration+'_lower'] = set(predicates[(len(predicates) // 2):])
    self.action_half_iteration = {}
    for hi, ps in self.half_iteration_actions.items():
      for p in ps:
        self.action_half_iteration[p] = hi

    self.action_requires = {a: set(self.action[a]['requires'])
                            for a in self.action}

    half_iteration_requires = {i: set() for i in self.half_iteration_actions}
    for a in self.action_requires:
      if a in self.action_iteration:
        half_iteration_requires[self.action_half_iteration[a]] |= self.action_requires[a]

    for iteration, requires in half_iteration_requires.items():
      for predicate in self.half_iteration_actions[iteration]:
        if predicate in self.action:
          self.action_requires[predicate] |= (half_iteration_requires[iteration] -
                                              self.half_iteration_actions[iteration])

  def __init__(self, config, engine, display_mode='colab', iterations=None):
    self.config = config
    self.recent_display_update_seconds = 0
    self.display_update_period = 0.0000000001
    self.iterations = iterations or {}
    self.action_iteration = None
    self.iteration_repetitions = None
    # Set of signals that were seen requesting a stop.
    # Once signal requests a stop, we have to stop whole iteration as some
    # process are already down.
    self.wrench_in_gears = set()
    self.action_requires = {}
    self.action = {a["name"]: a for a in self.config}
    self.action_stopped = set()
    self.UnderstandIterations()
    self.actions_to_run = self.SortActions()
    self.engine = engine
    assert len(self.action) == len(self.config)
    self.all_actions = {a["name"] for a in self.config}
    self.complete_actions = set()
    self.running_actions = set()
    assert display_mode in ('colab', 'terminal', 'colab-text', 'silent'), (
      'Unrecognized display mode: %s' % display_mode)
    self.display_mode = display_mode
    self.display_id = self.GetDisplayId()
    self.Display()

  def ActionIterationStopSignal(self, action):
    return self.iteration_stop_signal[self.action_iteration[action]]
  
  def ActionIterationWantsToStopBySignal(self, action):
    signal = self.ActionIterationStopSignal(action)
    if not signal:
      return False
    if signal in self.wrench_in_gears:
      return True
    if not os.path.isfile(signal):
      return False
    with open(signal) as f:
      s = f.read()
      if s:
        self.wrench_in_gears |= {signal}
        return True
      return False

  def UpdateStateForIterativeAction(self, one_action):
    # Marking action as complete, or incrementing its repetion count.
    # When incrementing repetion then cycling the iteration actions.
    self.action_iterations_complete[one_action] += 1
    if (self.action_iterations_complete[one_action] >=
        self.iteration_repetitions[self.action_iteration[one_action]]):
      self.complete_actions |= {one_action}
    elif self.ActionIterationWantsToStopBySignal(one_action):
      self.complete_actions |= {one_action}
      self.action_stopped |= {one_action}
    else:
      i = 0
      while (i < len(self.actions_to_run) and 
              self.actions_to_run[i] in self.action_iteration and
              self.action_iteration[self.actions_to_run[i]] ==
              self.action_iteration[one_action]):
        i += 1
      self.actions_to_run[i:i] = [one_action]

  def RunOneAction(self):
    # Probably updating display too often is only confusing.
    # self.UpdateDisplay()
    one_action = self.actions_to_run[0]
    del self.actions_to_run[0]
    self.running_actions |= {one_action}
    self.UpdateDisplay()
    self.engine.Run(self.action[one_action].get('action', {}))
    self.running_actions -= {one_action}
    if one_action not in self.action_iterations_complete:
      self.complete_actions |= {one_action}
    else:
      self.UpdateStateForIterativeAction(one_action)
    # self.UpdateDisplay()

  def Run(self):
    while self.actions_to_run:
      self.RunOneAction()
    self.UpdateDisplay(final=True)

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

  def IterationRepetitionsSymbol(self, iteration):
    if self.iteration_repetitions[iteration] > 1000000:
      return '∞'
    return '%d' % self.iteration_repetitions[iteration]

  def AsGraphViz(self):
    def NodeText(node):
      if node in self.action_iteration:
        maybe_iteration_info = ' %d / %s' % (
          self.action_iterations_complete[node],
          self.IterationRepetitionsSymbol(self.action_iteration[node])
        )
        if node in self.action_stopped:
          maybe_iteration_info += ' / stop.'
      else:
        maybe_iteration_info = ''
      return node + maybe_iteration_info
    g = graphviz.Digraph('Concertina')
    for a in self.all_actions:
      color = self.ActionColor(a)
      shape = self.ActionShape(a)
      styles = ['filled']

      g.node(NodeText(a), shape=shape, fillcolor=color, style='filled,rounded', color='gray34')
      for prerequisite in self.action[a]['requires']:
        g.edge(NodeText(prerequisite), NodeText(a))

    return g

  def AsTextPicture(self, updating):
    def AsArtGraph():
      nodes, edges = self.AsNodesAndEdges()
      return graph_art.Graph(nodes, edges)
    extra_lines = self.ProgressBar().split('\n')
    return AsArtGraph().GetPicture(updating=updating,
                                   extra_lines=extra_lines)

  def AsNodesAndEdges(self):
    """Nodes and edges to display in terminal."""
    def ColoredNode(node):
      if node in self.action_iteration:
        maybe_iteration_info = ' %d / %s' % (
          self.action_iterations_complete[node],
          self.IterationRepetitionsSymbol(self.action_iteration[node])
        )
        if node in self.action_stopped:
          maybe_iteration_info += ' / stop.'
      else:
        maybe_iteration_info = ' ' * 10
      if node in self.running_actions:
        if self.display_mode == 'terminal':
          return '\033[1m\033[93m' + node + maybe_iteration_info + '\033[0m'
        elif self.display_mode == 'colab-text':
          return (
            '<b>' + node + ' <= running</b>'
          )
        else:
          assert False, self.display_mode
      elif node in self.complete_actions and self.display_mode == 'colab-text' and self.actions_to_run:
        if node not in self.engine.completion_time:
          suffix = ' (input data)'
        else:
          suffix = ' (%d ms)' % self.engine.completion_time[node]
        return (
          '<span style="opacity: 0.6;">' + node + suffix + '</span>'
        )
      else:
        if node in self.complete_actions:
          if node not in self.engine.completion_time:
            suffix = ' (input data)'
          else:
            suffix = ' (%d ms)' % self.engine.completion_time[node]
        else:
          suffix = ''
        suffix += maybe_iteration_info
        return node + suffix

    nodes = []
    edges = []
    for a in self.all_actions:
      a_node = ColoredNode(a)
      nodes.append(a_node)
      for prerequisite in self.action[a]['requires']:
        prerequisite_node = ColoredNode(prerequisite)
        edges.append([prerequisite_node, a_node])
    return nodes, edges

  def AnalyzeWorkState(self):
    total_work = 0
    complete_work = 0
    for a in self.all_actions:
      if a in self.action_iteration:
        num_repetitions = self.iteration_repetitions[self.action_iteration[a]]
        total_work += num_repetitions
        if a in self.complete_actions:
          complete_work += num_repetitions
        else:
          complete_work += self.action_iterations_complete[a]
      else:
        total_work += 1
        complete_work += (a in self.complete_actions)
    return total_work, complete_work

  def ProgressBar(self):
    total_work, complete_work = self.AnalyzeWorkState()
    percent_complete = 100 * complete_work / total_work
    progress_bar = (
      '[' +
      '#' * (complete_work * 30 // total_work) +
      '.' * (30 - (complete_work * 30 // total_work)) +
      ']' + '  %.2f%% complete.' % percent_complete)
    if total_work == complete_work:
      progress_bar = '[' + 'Execution complete.'.center(30, ' ') + ']' + ' ' * 30
    return progress_bar

  def StateAsSimpleHTML(self):      
    style = ';'.join([
      'border: 1px solid rgba(0, 0, 0, 0.3)',
      'width: fit-content;',
      'padding: 20px',
      'border-radius: 5px',
      'min-width: 50em',
      'box-shadow: 1px 1px 3px rgba(0, 0, 0, 0.2)'])
    return HTML('<div style="%s"><pre>%s</pre></div>' % (
        style,
        self.AsTextPicture(updating=False)))

  def Display(self):
    if self.display_mode == 'colab':
      display(self.AsGraphViz(), display_id=self.display_id)
    elif self.display_mode == 'terminal':
      print(self.AsTextPicture(updating=False))
    elif self.display_mode == 'colab-text':
      display(self.StateAsSimpleHTML(),
              display_id=self.display_id)
    elif self.display_mode == 'silent':
      pass  # Nothing to display.
    else:
      assert 'Unexpected mode:', self.display_mode

  def UpdateDisplay(self, final=False):
    # This is now it's done, right?
    now = (datetime.datetime.now() -
           datetime.datetime(1, 12, 25)).total_seconds()
    # Trying to have the state on if the process fails at early step.
    self.display_update_period = min(0.5, self.display_update_period * 1.2)
    if (now - self.recent_display_update_seconds <
        self.display_update_period and
        not final):
      # Avoid frequent display updates slowing down execution.
      return
    self.recent_display_update_seconds = now
    if self.display_mode == 'colab':
      update_display(self.AsGraphViz(), display_id=self.display_id)
    elif self.display_mode == 'terminal':
      print(self.AsTextPicture(updating=True))
    elif self.display_mode == 'colab-text':
      update_display(
        self.StateAsSimpleHTML(),
        display_id=self.display_id)
    elif self.display_mode == 'silent':
      pass  # Nothing to display.
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
  iterations = {}
  for e in logica_executions:
    p_table_to_export_map, p_dependency_edges, p_data_dependency_edges = (
        e.table_to_export_map, e.dependency_edges, e.data_dependency_edges
    )
    for iteration in e.iterations:
      iterations[iteration] = e.iterations[iteration]
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
      print_running_predicate=(display_mode == 'colab'))

  preambles = set(e.preamble for e in logica_executions)
  # Due to change of types from predicate to predicate preables are not
  # consistent. However we expect preambles to be idempotent.
  # So we simply run all of them.
  # assert len(preambles) == 1, 'Inconsistent preambles: %s' % preambles
  # [preamble] = list(preambles)
  for preamble in preambles:
    if preamble:
      sql_runner(preamble, sql_engine, is_final=False)

  concertina = Concertina(config, engine,
                          iterations=iterations,
                          display_mode=display_mode)
  concertina.Run()
  return engine.final_result
