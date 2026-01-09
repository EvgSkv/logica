/*
Copyright 2025 Google LLC

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

     http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License. */


import * as duckdbduckdbWasm from "https://cdn.jsdelivr.net/npm/@duckdb/duckdb-wasm@latest/+esm";
window.duckdbduckdbWasm = duckdbduckdbWasm;

// Make db and conn accessible in the module scope
let db;
let conn;
// Add vars for Pyodide
let pyodide;
let pyodideCompile;

// This is where we'll store compiled SQL
window.program_sql = {};

const outDiv = {innerHTML: ''};
//document.getElementById("out");

/**
 * A replacer function for JSON.stringify to handle BigInts.
 */
const jsonReplacer = (key, value) => {
  if (typeof value === 'bigint') {
    // Convert BigInts to strings
    return value.toString();
  }
  return value;
};

/**
 * Writes an array of JS objects to a DuckDB table.
 * @param {string} table_name The name of the table to create.
 * @param {Object[]} records An array of simple JavaScript objects.
 */
export async function WriteTable(table_name, records) {
  if (!db || !conn) {
    throw new Error("DuckDB is not initialized.");
  }
  if (!Array.isArray(records) || records.length === 0) {
    throw new Error("Records must be a non-empty array.");
  }
  // console.log('About to create table ', table_name)
  try {
    // Use the global replacer
    const json_string = JSON.stringify(records); //JSON.stringify(records, jsonReplacer);
    const json_file_name = `${table_name}.json`;

    // Drop table if it exists
    await conn.query(`DROP TABLE IF EXISTS ${table_name}`);

    //console.log('Table dropped.');

    // Register the JSON string as a file
    await db.registerFileText(json_file_name, json_string);

    //console.log('Registered:', json_string);
    // Create the table from the JSON file
    await conn.query(
      `CREATE TABLE ${table_name} AS SELECT * FROM read_json_auto('${json_file_name}')`
    );

    // console.log(`Table '${table_name}' created successfully.`);
    return true;
  } catch (error) {
    console.error(`Error in WriteTable(${table_name}):`, error);
    throw error;
  }
}

/**
 * Runs the test: writes a table, reads from it, and shows output.
 */
function runTest() { // No longer async
  outDiv.innerHTML = "Creating test table...";

  // 1. Define sample data
  const testData = [
    { name: "Alice", age: 30, city: "New York" },
    { name: "Bob", age: 25, city: "London" },
  ];
  const tableName = "People";

  // 2. Call WriteTable and chain .then()
  // We return the promise chain
  return WriteTable(tableName, testData)
    .then(() => {
      // This block runs after WriteTable is successful
      outDiv.innerHTML = "Table created. Reading data...";

      // 3. Read data back, returning the next promise
      // Removed the cast(age as int32) and selecting all columns
      return conn.query(`SELECT * FROM ${tableName}`);
    })
    .then((results) => {
      // This block runs after the query is successful
      const dataArray = results.toArray().map((row) => row.toJSON());

      // 4. Display results in HTML
      // Use the replacer here as well!
      outDiv.innerHTML = `
        <h2>Table '${tableName}' created and read successfully!</h2>
        <pre>${JSON.stringify(dataArray, jsonReplacer, 2)}</pre>
      `;
    })
    .catch((error) => {
      // This .catch() replaces the try/catch block
      console.error("Test failed:", error);
      outDiv.innerHTML = `
        <h2>Test Failed</h2>
        <pre style="color: red;">${error.message}</pre>
      `;
    });
}

/**
 * Initializes Pyodide and loads Logica.
 */
async function initializePyodide() {
  outDiv.innerHTML += "<p>Loading Pyodide...</p>";

  // **FIX:** Redirect stdout/stderr to console
  pyodide = await loadPyodide({
    stdout: (text) => console.log("[Pyodide STDOUT]", text),
    stderr: (text) => console.error("[Pyodide STDERR]", text),
  });

  outDiv.innerHTML += "<p>Pyodide loaded. Loading micropip...</p>";
  await pyodide.loadPackage("micropip"); // <-- TYPO FIX
  const micropip = pyodide.pyimport("micropip");

  outDiv.innerHTML += "<p>Installing Logica...</p>";
  // From your example, we also need sqlite3
  //await micropip.install(["logica", "sqlite3"]);
  await micropip.install(["sqlite3"]);

  const logica_response = await fetch('logica3.zip');
  const logica_arrayBuffer = await logica_response.arrayBuffer();
  const logica_uint8Array = new Uint8Array(logica_arrayBuffer);

  await pyodide.unpackArchive(logica_uint8Array, 'zip');

  outDiv.innerHTML += "<p>Logica installed. Defining compiler...</p>";

  // Define the Python helper function
  pyodide.runPython(`
import sys
from logica.parser_py import parse
from logica.compiler import universe
from logica.common import logica_lib
from logica.common import color
print("Python: Defining compile_predicate_to_sql...")

color.CHR_ERROR = '<span style="color: red">'
color.CHR_WARNING =  '<span style="color: yellow">'
color.CHR_UNDERLINE =  '<span style="color: white">'
color.CHR_END = '</span>'
color.CHR_OK =  '<span style="color: green">'

def compile_predicate_to_sql(logica_code, predicate_name):
  try:
    print(f"Python: Compiling predicate '{predicate_name}'...")
    # Add the @Engine pragma for DuckDB
    program_with_pragma = '@Engine("duckdb");\\n' + logica_code
    rules = parse.ParseFile(program_with_pragma)['rule']
    program = universe.LogicaProgram(rules)

    if not rules:
        print("Python: No rules found.")
        return {"sql": None, "error": "No Logica rules found."}

    sql = program.FormattedPredicateSql(predicate_name)
    print(f"Python: Compiled SQL: {sql}")
    return {"sql": sql, "error": None}
  except Exception as e:
    print(f"Python: Compilation error: {e}")
    # Generic fallback
    error_message = str(e)
    try: 
      import io
      s = io.StringIO()
      e.ShowMessage(s)
      error_message = s.getvalue()
      error_message = error_message.replace('\\n', '<br/>')
    except Exception as ee:
      pass
    return {"sql": None, "error": error_message}
  `);

  // Get a JS handle to the Python function
  pyodideCompile = pyodide.globals.get("compile_predicate_to_sql");

  outDiv.innerHTML += "<p>Logica compiler is ready.</p>";
}

/**
 * Compiles a Logica predicate and stores the SQL.
 * @param {string} logica_program The full Logica program string.
 * @param {string} predicate The name of the predicate to compile.
 */
export function Compile(logica_program, predicate) { // <-- REMOVED ASYNC
  if (!pyodideCompile) {
    throw new Error("Pyodide compiler is not initialized.");
  }

  console.log(`Compiling predicate: ${predicate}`);
  const resultProxy = pyodideCompile(logica_program, predicate);

  // **FIX:** Use .get() instead of .toJs()
  const error = resultProxy.get("error");
  const sql_result = resultProxy.get("sql");
  resultProxy.destroy();

  if (error) {
    // throw new Error(`Logica compilation failed: ${error}`);
    // Drop the book, it's cleaner.
    throw new Error(`${error}`);
  }

  // **FIX:** Check if sql_result is null or undefined
  if (!sql_result) {
    throw new Error(`Logica compilation for '${predicate}' produced no SQL. Check your Logica rules for errors.`);
  }

  const sql = sql_result;
  window.program_sql[predicate] = sql;
  console.log(`Compiled SQL for ${predicate}:`, sql);
  return sql; // <-- Returns a string, not a promise
}

/**
 * Executes a previously compiled predicate.
 * @param {string} predicate The name of the predicate to execute.
 */
export async function Execute(predicate) {
  const sql = window.program_sql[predicate];
  if (!sql) {
    throw new Error(`No compiled SQL found for predicate: ${predicate}`);
  }

  // console.log(`Executing predicate: ${predicate}`);
  // console.log('SQL:', sql);
  const results = await conn.query(sql);
  return results.toArray().map((row) => row.toJSON());
}

/**
 * Runs the Logica test: Compiles and executes a Logica program.
 */
function runLogicaTest() {
  outDiv.innerHTML += "<h2>Running Logica Test</h2>";

  const logicaProgram = `
# Define a predicate that uses the 'People' table
OlderThan(name:, age:) :-
People(name:, age:),
age > 28;

# Define the main query predicate
Query(name:, age:) :- OlderThan(name:, age:);
    `;

  const predicateToRun = "Query";

  // 1. Compile the predicate (synchronously)
  // We wrap the sync call in a Promise to keep the chain
  return new Promise((resolve, reject) => {
    try {
      const compiledSql = Compile(logicaProgram, predicateToRun);
      resolve(compiledSql);
    } catch (err) {
      reject(err);
    }
  })
    .then((compiledSql) => {
      // This block runs after Compile is successful
      outDiv.innerHTML += `
        <p>Logica predicate '${predicateToRun}' compiled successfully:</p>
        <pre style="background: #eee; padding: 5px;">${compiledSql}</pre>
      `;

      // 2. Execute the predicate (this is async)
      return Execute(predicateToRun);
    })
    .then((dataArray) => {
      // This block runs after Execute is successful
      outDiv.innerHTML += `
        <p>Execution results for '${predicateToRun}':</p>
        <pre>${JSON.stringify(dataArray, jsonReplacer, 2)}</pre>
      `;
    })
    .catch((error) => {
      // This .catch() handles errors from Compile or Execute
      console.error("Logica test failed:", error);
      outDiv.innerHTML += `
        <h2>Logica Test Failed</h2>
        <pre style="color: red;">${error.message}</pre>
      `;
    });
}


// This function remains the same as your example
const getDb = async () => {
  const duckdb = window.duckdbduckdbWasm;
  // @ts-ignore
  if (window._db) return window._db;
  const JSDELIVR_BUNDLES = duckdb.getJsDelivrBundles();

  // Select a bundle based on browser checks
  const bundle = await duckdb.selectBundle(JSDELIVR_BUNDLES);

  const worker_url = URL.createObjectURL(
    new Blob([`importScripts("${bundle.mainWorker}");`], {
      type: "text/javascript",
    })
  );

  // Instantiate the asynchronous version of DuckDB-wasm
  const worker = new Worker(worker_url);
  const logger = new duckdb.ConsoleLogger(duckdb.LogLevel.ERROR);
  const db = new duckdb.AsyncDuckDB(logger, worker);
  await db.instantiate(bundle.mainModule, bundle.pthreadWorker);
  URL.revokeObjectURL(worker_url);
  window._db = db;
  return db;
};

export async function Init() {
  // getDb().then(async (database) => {
  //   db = database;
  //   // Create a new connection
  //   conn = await db.connect();
  //   console.log('Connection complete.');
  // });
  db = await getDb();
  conn = await db.connect();
  console.log('DuckDB Connection complete.');

  // **THE FIX IS HERE:**
  // We must also initialize Pyodide before Init is "done".
  await initializePyodide();
  
  // console.log('Connection complete.'); // Old log
  console.log('Full Initialization complete (DuckDB + Pyodide).'); // New log
}

// **THE FIX IS HERE:**
export function RunTests() {
  // Main execution
  getDb().then(async (database) => {
    db = database;
    // Create a new connection
    conn = await db.connect();

    // Run the table test first
    await runTest();

    // Now, initialize Pyodide
    await initializePyodide();

    // Finally, run the Logica test
    // We await the .then() chain
    await runLogicaTest(); // <-- TYPO FIX

    // Original test code (can be removed or kept)
    console.log("Running original generate_series test...");
    const stmt = await conn.prepare(
      `SELECT v + ? as t FROM generate_series(0, 5) AS t(v);` // shortened to 5
    );
    let res = (await stmt.query(234)).toArray();
    console.log("generate_series result:", res);

  }).catch(err => {
    console.error("Initialization or main execution failed:", err);
    outDiv.innerHTML = `<h2 style="color: red;">Failed to initialize: ${err.message}</h2>`;
  });
}

