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


/**
 * This module acts as the "brain" for the robots.
 * It takes sensor and memory data from the simulation,
 * runs it through a Logica program, and returns the
 * calculated desires and new memory.
 */
import * as l from "./logica_lib.js";

// --- State ---
let defaultProgram = `

@Ground(Robot);
Robot(robot_name:,
      desire: {
        left_engine:,
        right_engine:
      },
      memory:) :-
  Memory(robot_name:, memory: old_memory),  
  # Just pass memory forward, or reset to remember Earth.
  memory = Coalesce(old_memory, {motherland: "Earth"}),
  Sensor(robot_name:, sensor:),
  forward_distance = sensor.forward_distance,
  ((
    forward_distance > 50,
    left_engine = 1.0,
    right_engine = 1.0
  ) | (
    # Turning one way for now.
    forward_distance <= 50,
    left_engine = -0.5,
    right_engine = -0.5
  ));

RobotJson(robot_name:, desire: RecordAsJson(desire), memory: RecordAsJson(memory)) :-
  Robot(robot_name:, desire:, memory:);

`; // Will be set by SetDefaultProgram
let currentProgram = defaultProgram;
let isCompiled = false;

/**
 * Sets the default Logica program.
 * @param {string} program_string 
 */
export function SetDefaultProgram(program_string) {
    defaultProgram = program_string;
    currentProgram = program_string;
    isCompiled = false;
}

/**
 * Compiles a new Logica program.
 * If compilation fails, it reverts to the default program.
 * @param {string} logica_program 
 */
export function Compile(logica_program) {
    try {
        l.Compile(logica_program, 'RobotJson');
        currentProgram = logica_program;
        isCompiled = true;
        console.log("LogicaBrain: New program compiled successfully.");
    } catch (e) {
        console.error("LogicaBrain: Compilation Error. Reverting to default.", e);
        // Revert to default
        try {
            l.Compile(defaultProgram, 'RobotJson');
            currentProgram = defaultProgram;
            isCompiled = true;
        } catch (defaultError) {
            console.error("LogicaBrain: FATAL. Default program also failed to compile.", defaultError);
            isCompiled = false;
        }
        throw e; // Re-throw the original error to notify the UI
    }
}

/**
 * Gets the desires for all robots.
 * @param {Array} sensors_data [{robot_name: string, sensor: {forward_distance: number}}, ...]
 * @param {Array} memory_data [{robot_name: string, memory: object_or_null}, ...]
 * @returns {Promise<{desires: Map<string, object>, memories: Map<string, object>}>}
 */
export async function Desire(sensors_data, memory_data) {
    if (!isCompiled) {
        console.warn("LogicaBrain: Program not compiled, compiling default.");
        if (!defaultProgram) {
            console.error("LogicaBrain: No default program set.");
            return { desires: new Map(), memories: new Map() };
        }
        Compile(defaultProgram);
    }
    // console.log('-------------Desire running!----------');
    // console.log('Sensors:', sensors_data);
    // console.log('Memory:', memory_data);
    // 1. Prepare data for DuckDB
    // We can pass these directly to WriteTable
    const sensor_table_data = [...sensors_data]; 
    const memory_table_data = [...memory_data]; 

    // Extract robot names from the sensor data array
    const robot_names = sensors_data.map(entry => entry.robot_name);
    const robot_count = robot_names.length;

    // 2. Write data to DuckDB tables
    try {
        await l.WriteTable('Sensor', sensor_table_data);
        await l.WriteTable('Memory', memory_table_data);
    } catch (e) {
        console.error("LogicaBrain: Error writing tables.", e);
        // Return empty maps so the simulation doesn't crash
        return { desires: new Map(), memories: new Map() };
    }

    // 3. Execute the compiled Logica predicate
    let logica_results = [];
    //try {
        logica_results = await l.Execute('RobotJson');
    //} catch (e) {
    //    console.error("LogicaBrain: Error executing Logica predicate.", e);
    //    // Return empty maps
    //    return { desires: new Map(), memories: new Map() };
    //}
    // console.log('Will try parsing.', logica_results);

    // console.log('>>', JSON.stringify(logica_results, null, 2));
    // 4. Process results into maps
    // This map is critical for an O(1) lookup of results by robot_name.
    const desireMap = new Map(logica_results.map(r => [r.robot_name, r]));
    
    // console.log('Desire map:', desireMap);

    const desires = new Map();
    const memories = new Map();
    
    // console.log(' I have robots:', robot_names);
    for (let i = 0; i < robot_count; i++) {
        const current_robot_name = robot_names[i];
        
        // Find the result by the robot's actual name
        const result = desireMap.get(current_robot_name);
        
        // console.log('Result:::', result);
        if (result) {
            // Success: Logica returned a desire for this robot
            desires.set(current_robot_name, JSON.parse(result.desire));
            memories.set(current_robot_name, result.memory);
        }
    }
    // console.log('Returning:', desires, memories);
    
    return { desires: desires, memories: memories };
}

// --- Test Suite ---

/**
 * Runs a suite of tests against the Desire function
 * and logs the inputs and outputs.
 * Assumes SetDefaultProgram has been called.
 */
export function RunTests() {
    console.log("--- Running LogicaBrain Tests ---");

    const log = console.log;
    
    // --- Test Scenario 1 ---
    log("Running Test 1: Two robots, wall / clear path.");
    const test_sensors_1 = [
        { robot_name: "Alpha", sensor: { forward_distance: 30 } },
        { robot_name: "Beta", sensor: { forward_distance: 100 } }
    ];
    const test_memory_1 = [
        { robot_name: "Alpha", memory: null },
        { robot_name: "Beta", memory: { "motherland": "Earth" } }
    ];
    
    log("  Test 1 Inputs:");
    log(`    Sensors: ${JSON.stringify(test_sensors_1)}`);
    log(`    Memory: ${JSON.stringify(test_memory_1)}`);

    // Call Desire, which returns a promise.
    // We chain our logic to that promise.
    Desire(test_sensors_1, test_memory_1)
        .then(
            // This function runs when the promise succeeds (Test 1 Outputs)
            (dm) => {
                log("DM:", dm);
                let desires = dm.desires;
                let memories = dm.memories;
                log("  Test 1 Outputs:");
                log("    Desires Map:", desires);
                log("    Memories Map:", memories);

                // --- Test Scenario 2 ---
                // We *must* nest Test 2 inside the .then() of Test 1
                // to guarantee they run in the correct order.
                log("Running Test 2: Three robots, one new.");
                const test_sensors_2 = [
                    { robot_name: "Alpha", sensor: { forward_distance: 20 } },
                    { robot_name: "Beta", sensor: { forward_distance: 80 } },
                    { robot_name: "Gamma", sensor: { forward_distance: 120 } }
                ];
                const test_memory_2 = [
                    { robot_name: "Alpha", memory: { "motherland": "Mars" } },
                    { robot_name: "Beta", memory: { "motherland": "Venus" } },
                    { robot_name: "Gamma", memory: null } // New robot
                ];

                log("  Test 2 Inputs:");
                log(`    Sensors: ${JSON.stringify(test_sensors_2)}`);
                log(`    Memory: ${JSON.stringify(test_memory_2)}`);

                // We return the promise from the *next* call to Desire
                return Desire(test_sensors_2, test_memory_2);
            }
        )
        .then(
            // This .then() is chained to the promise returned by Test 1's block
            // It receives the results from Test 2
            (dm) => {
                log("DM:", dm);
                let desires = dm.desires;
                let memories = dm.memories;
                log("  Test 2 Outputs:");
                log("    Desires Map:", desires);
                log("    Memories Map:", memories);

                log("--- Test Run Complete ---");
            }
        )
        .catch(
            // This single .catch() will handle errors from *any*
            // of the promises in the chain (Test 1 or Test 2)
            (e) => {
                console.error("  Test Run: Uncaught Error", e);
                console.log("--- Test Run Failed ---");
            }
        );
}

