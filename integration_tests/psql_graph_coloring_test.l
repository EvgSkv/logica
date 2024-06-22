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

@Engine("psql");
# Signa inter verba conjugo, symbolum infixus evoco!

##################
# Defining graph

-+-(left:x, right:y) = ToString(x) ++ ":" ++ ToString(y);
G("a" -+- i, "a" -+- (i + 1)) :- i in Range(6);

@Recursive(L, 8, iterative: true);
L(1, 1, 2, 1) distinct;
L(x, y, x * 2, y) distinct :- L(a, b, x, y);
L(x, y, x, y * 3) distinct :- L(a, b, x, y);

G("b" -+- x -+- y, "b" -+- x1 -+- y1) :- L(x, y, x1, y1), x < 6, y < 6;

E(a, b) :- G(a, b) | G(b, a);


#################################
# Finding connected components.
#

@Recursive(ComponentOf, 25);
ComponentOf(x) Min= x :- E(x);
ComponentOf(x) Min= ComponentOf(y) :- E(x, y);

ComponentStart() = ComponentOf() distinct;

#######################
# Coloring the graph.

White() = "#eee";
Black() = "#bbb";
    
Other(White()) = Black();
Other(Black()) = White();
    
@Recursive(Color, 30);
Color(ComponentStart()) = White() distinct;
Color(y) = Other(Color(x)) distinct :- E(x, y);

######################
# Building verdict.
ColorableVerdict() = (
    if Max{Count{Color(vertex)} :- E(vertex)} == 1 then
      "colorable"
    else
      "not colorable");

###########################
# Coloring another graph.

G2(a, b) :- G(a, b) | a = "a:0", b = "a:6";
ColorableVerdict2 := ColorableVerdict(G: G2);

########################
# Assembling the test.  
  
@OrderBy(Test, "col0");
Test("G1", ColorableVerdict());
Test("G2", ColorableVerdict2());
