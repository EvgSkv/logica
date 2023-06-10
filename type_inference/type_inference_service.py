from typing import cast

from type_inference.inspectors.inspector_base import Inspector
from type_inference.intersection import Intersect, IntersectListElement
from type_inference.types.edge import Equality, EqualityOfElement, FieldBelonging
from type_inference.types.expression import PredicateAddressing, Variable
from type_inference.types.types_graph import TypesGraph
from type_inference.types.variable_types import AnyType, ListType, RecordType


class TypeInference:
  def __init__(self, graphs: dict, inspector: Inspector = None):
    self.inspector = inspector
    self.all_edges = []
    for graph in graphs.values():
      self.all_edges.extend(graph.ToEdgesSet())
    self.MergeGraphs(graphs)

  def FindField(self, field_name: str, graph: TypesGraph):
    tmp_var = Variable(field_name)
    edge = list(graph.expression_connections[tmp_var].values())[0][0]
    if edge.vertices[0] == tmp_var:
      return edge.vertices[0]
    else:
      return edge.vertices[1]

  def MergeGraphs(self, graphs: dict):
    edges_to_add = []
    for g in graphs.values():
      for p in g.expression_connections.keys():
        if isinstance(p, PredicateAddressing) and p.type == AnyType():
          if p.predicate_name in graphs:
            to_link = self.FindField(p.field, graphs[p.predicate_name])
            edges_to_add.append(Equality(p, to_link, (-1, -1)))
          else:
            column_info = self.inspector.TryGetColumnsInfo(p.predicate_name)
            p.type = column_info[p.field]
    self.all_edges.extend(edges_to_add)

  def Infer(self):
    changed = True
    while changed:
      changed = False
      for edge in self.all_edges:
        if isinstance(edge, Equality):
          edge = cast(Equality, edge)
          left, right = edge.left.type, edge.right.type
          result = Intersect(left, right)
          if result != edge.left.type:
            edge.left.type = result
            changed = True
          if result != edge.right.type:
            edge.right.type = result
            changed = True
        elif isinstance(edge, EqualityOfElement):
          edge = cast(EqualityOfElement, edge)
          if isinstance(edge.list.type, AnyType):
            edge.list.type = ListType(AnyType())
          left, right = edge.element.type, cast(ListType, edge.list.type)
          result = IntersectListElement(right, left)
          if result != edge.element.type:
            edge.element.type = result
            changed = True
          if ListType(result) != edge.list.type:
            edge.list.type = ListType(result)
            changed = True
        elif isinstance(edge, FieldBelonging):
          edge = cast(FieldBelonging, edge)
          if isinstance(edge.parent.type, AnyType):
            edge.parent.type = RecordType({}, True)
          record = cast(RecordType, edge.parent.type)
          field_name = edge.field.subscript_field
          if field_name in record.fields:
            result = Intersect(edge.field.type, record.fields[field_name])
            if result != record.fields[field_name]:
              changed = True
              record.fields[field_name] = result
          else:
            changed = True
            record.fields[field_name] = edge.field.type
