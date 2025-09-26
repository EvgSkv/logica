/*
Copyright 2023 Google LLC

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

     http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License. */


function HighlightCodeElements(doc) {
  console.log('HELLO!');
  synt_obj = {
      multiline_comment: /\/\*.*\*\//gs,
      end_of_line_comment: /#.*/g,
      operator: /&gt;|&lt;/g,
      string: /["].*?["]/g,
      numeric_literal: /\b[0-9]+[.]?[0-9]*/g,
      predicate: /[A-Z]\w*/g,
      field: /\w+:/g,
      agg_field: /\w+[?]/g,
      keyword: /\bif | then | else | distinct | in /g,
      variable: /[a-z]\w*/g
  };

  function Decorate(s, r, prefix, suffix, subdecor) {
      let result = ''
      let from_index = 0;
      s.replace(r, (match, at, unused_s) => {
          result += subdecor(s.slice(from_index, at));
          result += prefix + match + suffix;
          from_index = at + match.length;
          return '';
      });

      result += subdecor(s.slice(from_index, s.length));
      return result;
  }

  var syntax_elements = Object.entries(synt_obj);

  function MakeDecorator(syntax_elements) {
      let n, r, rest;
      [[n, r], ...rest] = syntax_elements;

      let subdecorator;
      if (rest.length > 0) {
          subdecorator = MakeDecorator(rest);
      } else {
          subdecorator = x => x;
      }
      return s => Decorate(s, r, `<div class="${n}">`, `</div>`, subdecorator);
  }

  function HighlightLogicaCode(code) {
    highlighter = MakeDecorator(syntax_elements);
    return highlighter(code);
  }

  divs = doc.getElementsByClassName('code');
  for (let d of divs) {
    d.innerHTML = HighlightLogicaCode(d.innerText);
  }
}