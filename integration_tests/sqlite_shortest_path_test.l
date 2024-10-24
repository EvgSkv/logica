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

# This example was causing record unfolding go wild.

@Engine("sqlite", type_checking: true);

Edge("a", "b");
Edge("b", "c");
Edge("c", "d");
Edge("d", "e");
Edge("d", "a");

`*`(open_path) = ArgMin(k -> v).nodes :-
    k == {nodes: open_path},
    v == Size(open_path);

OpenPath(start, end) *= [start] :-
    (Edge(start, end) | Edge(end, start));

OpenPath(start, end) *= ArrayConcat(path_one, path_two) :-
  OpenPath(start, intermediate_node) = path_one,
  OpenPath(intermediate_node, end) = path_two,
  start != end;

Test(a, b, OpenPath(a, b));