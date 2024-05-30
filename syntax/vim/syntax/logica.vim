" Copyright 2020 Google LLC
"
" Licensed under the Apache License, Version 2.0 (the "License");
" you may not use this file except in compliance with the License.
" You may obtain a copy of the License at
"
"      http://www.apache.org/licenses/LICENSE-2.0
"
" Unless required by applicable law or agreed to in writing, software
" distributed under the License is distributed on an "AS IS" BASIS,
" WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
" See the License for the specific language governing permissions and
" limitations under the License.

" Vim syntax file
" Language: Logica

if exists("b:current_syntax")
  finish
endif

syntax case match

syntax region logicaComment start=+/\*+ end=+\*/+
syntax match logicaComment +#.*$+
syntax match logicaAnnotation +@[_a-zA-Z$][_a-zA-Z0-9$]*\>+
syntax match logicaString +"\(\\"\|[^"]\)*"+

" Symbol
syntax match logicaSymbol +'[_a-zA-Z$][_a-zA-Z0-9$]*+

" Global variables
syntax match logicaGlobal +[A-Z$][_a-zA-Z0-9$]*+
syntax match logicaGlobal +\^[a-z][_a-zA-Z0-9$]*+

" Local variables
syntax match logicaVariable +[a-z][_a-zA-Z0-9$]*+

" Wildcard Variables
syntax match logicaWildcard +_[_a-zA-Z0-9$]*+

" Fields
syntax match logicaField +[0-9a-zA-Z_$]*:+
syntax match logicaField +[0-9a-zA-Z_$]*[?]+

" Integers
syntax match logicaInteger +0\|[1-9][0-9]*+
syntax match logicaInteger +0x[0-9a-fA-F]\++

syntax keyword logicaNull null
syntax keyword logicaBoolean true false
syntax keyword logicaKeyword combine
syntax keyword logicaKeyword distinct import as
syntax keyword logicaGoal if then else
syntax keyword logicaKeyword in

let b:current_syntax = "logica"

" Highlighting Links

hi def link logicaGlobal Type
hi def link logicaVariable Identifier
hi def link logicaWildcard Identifier

hi def link logicaSymbol Constant
hi def link logicaBoolean Boolean
hi def link logicaInteger Number
hi def link logicaNull Constant
hi def link logicaKeyword Keyword
hi def link logicaGoal Conditional
hi def link logicaReserved Error
hi def link logicaField Special

hi def link logicaString String
hi def link logicaRawString String
hi def link logicaComment Comment
hi def link logicaAnnotation Define
