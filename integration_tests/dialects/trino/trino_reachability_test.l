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

# Testing recursive path finding in Trino.

@Engine("trino");
@Dataset("memory.logica");

G(1, 2);
G(2, 3);
G(3, 4);
G(3, 5);
G(1, 8);

C(a, b) distinct :- G(a, b) | G(b, a);

@Ground(Path);
Path(source:, target:, length? Min= 1,
     path? ArgMin= ([source] -> 1)) distinct :-
  C(source, target);

Path(source: a, target: c,
     length? Min= l1 + l2,
     path? ArgMin= ArrayConcat(p1, p2) -> (l1 + l2)) distinct :-
  Path(source: a, target: b, length: l1, path: p1),
  Path(source: b, target: c, length: l2, path: p2);

@OrderBy(FinalPath, "source", "target");
FinalPath(source:, target:, final_path:) :-
  Path(source:, target:, path:),
  final_path == ArrayConcat(path, [target]),
  source != target;

Test := FinalPath();
