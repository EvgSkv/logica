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

// Module to run predicates asynchronously.

importScripts("https://cdn.jsdelivr.net/pyodide/v0.23.2/full/pyodide.js");


loadPyodide().then((x) => {
    self.pyodide = x;
}).then(() => {
    return self.pyodide.loadPackage('micropip');
}).then(() => {
    return self.pyodide.pyimport('micropip');
}).then((micropip) => {
    return micropip.install(['logica', 'sqlite3']);
}).then(() => {
    Init();
});

function Init() {
    self.pyodide.runPython(pythonScript);
    self.run_predicate = self.pyodide.globals.get('RunPredicate');
}

self.onmessage = function(event) {
    console.log('Logical worker got event:', event);
    let data = event.data;
    if (data.type == 'run_predicate') {
        console.log('Running predicate...');
        let program = data.program;
        let predicate = data.predicate;
        let result = self.run_predicate(program, predicate).toJs(); //program, predicate)
        result.set('hide_error', data.hide_error);
        result.set('program', program);
        result.set('predicate', predicate);
        // console.log('Result:', result);
        self.postMessage(result);
        console.log('Predicate execution is complete.');
    } else {
        console.log('Received an unrecognized message:', event.data);
    }
};

const pythonScript = `
print('Logical engine intialzing.')

from logica.parser_py import parse
from logica.compiler import universe
from logica.compiler import rule_translate
from logica.common import logica_lib
from logica.common import color

color.CHR_WARNING = '{logica error}-*'
color.CHR_END = '*-{logica error}'

import csv

def CreateBooksCsvFile():
    with open('books.csv', 'w') as w:
        writer = csv.writer(w)
        # It's easier to parse without header and it is
        # impossible to use the header anyway.
        # writer.writerow(['name', 'author', 'price'])
        writer.writerow(['From Caves to Stars', 'Beans A.A.', 120])
        writer.writerow(['Morning of Juliet', 'Smitey E.', 40])
        writer.writerow(['Dawn of the Apes', 'Mon K.', 45])
        writer.writerow(['Tragedy and Discord', 'Tarklor D.', 124])
        writer.writerow(['How to Get Rich Writing Book for $5', 'Getri C. H.', 5])
        writer.writerow(['I Wrote a Book for $5 - Guess What Happened Next!', 'Getri C. H.', 4])
        writer.writerow(['Breakfast at Paris', 'Degaul C.', 30])
        writer.writerow(['My Friend: Dragon', 'Tame R.', 102])

CreateBooksCsvFile()


def RunPredicate(program, predicate):
    program = '@Engine("sqlite");' + program;
    try:
      rules = parse.ParseFile(program)['rule']
    except parse.ParsingException as e:
      before, error, after = e.location.Pieces()
      error_context = before + "{logica error}-*" + error + "*-{logica error}" + after;
      return {"result": "", "error_context": error_context, "error_message": str(e), "status": "error", "predicate_name": predicate}
    try:
      u = universe.LogicaProgram(rules)
      sql = u.FormattedPredicateSql(predicate)
    except rule_translate.RuleCompileException as e:
      return {"result": "", "error_context": e.rule_str, "error_message": str(e), "status": "error", "predicate_name": predicate}

    try:
      data = logica_lib.RunQuery(sql, engine='sqlite')
    except Exception as e:
      return {"result": "", "error_context": sql, "error_message": "Error while executing SQL:\\n" + str(e), "status": "error", "predicate_name": predicate}


    return {"result": data, "error_message": "",  "error_context": "", "status": "OK", "predicate_name": predicate}
`;