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


// --- Setup ---
const canvas = document.getElementById('editorCanvas');
const ctx = canvas.getContext('2d');
const brushSlider = document.getElementById('brushSize');
const toolMode = document.getElementById('toolMode');
const downloadButton = document.getElementById('downloadButton');
const loadButton = document.getElementById('loadButton');
const fileInput = document.getElementById('fileInput'); 

// --- Alert Modal elements ---
const alertModal = document.getElementById('alertModal');
const alertMessage = document.getElementById('alertMessage');
const alertClose = document.getElementById('alertClose');

// --- Edit Modal elements ---
const editModal = document.getElementById('editModal');
const editTitle = document.getElementById('editTitle');
const editName = document.getElementById('editName');
const editColor = document.getElementById('editColor');
const editColorRow = document.getElementById('editColorRow');
const saveEdit = document.getElementById('saveEdit');
const deleteEdit = document.getElementById('deleteEdit');
const closeEdit = document.getElementById('closeEdit');
const editAngleRow = document.getElementById('editAngleRow');
const editAngle = document.getElementById('editAngle');
const editRadiusRow = document.getElementById('editRadiusRow');
const editRadius = document.getElementById('editRadius');
// Angle Editor elements
const angleEditorRow = document.getElementById('angleEditorRow');
const angleEditor = document.getElementById('angleEditor');
const angleEditorCtx = angleEditor.getContext('2d');

// --- NEW: Area-specific edit elements ---
const editVictoryRobotsRow = document.getElementById('editVictoryRobotsRow');
const editVictoryRobots = document.getElementById('editVictoryRobots');
const editOnBeaconRow = document.getElementById('editOnBeaconRow');
const editOnBeacon = document.getElementById('editOnBeacon');
const editOffBeaconRow = document.getElementById('editOffBeaconRow');
const editOffBeacon = document.getElementById('editOffBeacon');
const editStickySwitchRow = document.getElementById('editStickySwitchRow');
const editStickySwitch = document.getElementById('editStickySwitch');
// --- *** 1. ADDED IMPENETRABLE ELEMENTS *** ---
const editImpenetrableRow = document.getElementById('editImpenetrableRow');
const editImpenetrable = document.getElementById('editImpenetrable');
// --- END NEW ---

// --- Resize Modal elements ---
const resizeModal = document.getElementById('resizeModal');
const resizeButton = document.getElementById('resizeButton');
const resizeWidth = document.getElementById('resizeWidth');
const resizeHeight = document.getElementById('resizeHeight');
const cancelResize = document.getElementById('cancelResize');
const applyResize = document.getElementById('applyResize');

// --- MODIFIED: Labyrinth dimensions are now dynamic ---
let LABYRINTH_WIDTH = 500;
let LABYRINTH_HEIGHT = 500;

// --- State ---
let brushRadius = parseInt(brushSlider.value, 10);
let isDrawing = false;
let currentTool = 0; 
let selectedObjectIndex = -1;
let selectedObjectType = null; // 'robot', 'beacon', or 'area'
let isDraggingAngle = false;

// --- MODIFIED: State variables are declared, not initialized ---
let grid;    // 2D array [y][x]
let robots;  // Array of {x, y, name, color, angle (in RADIANS)}
let beacons; // Array of {x, y, name}
let areas;   // MODIFIED: Array of {x, y, name, color, radius, victory_robots, on_beacon, off_beacon, sticky_switch}
let imageData; // 1D array for canvas pixels

// Colors (RGBA)
const WALL_COLOR = [0, 0, 0, 255];     // Black
const PATH_COLOR = [70, 70, 70, 255]; // Dark Grey (#464646)

// Object drawing constants
const ROBOT_RADIUS = 5;
const BEACON_SIZE = 4; // Half-size (total size 8x8)
const BEACON_COLOR = '#00FF00'; // Bright green
const DEFAULT_AREA_COLOR = '#FFFF00'; // Yellow

// Custom alert function
function customAlert(message) {
    alertMessage.textContent = message;
    alertModal.style.display = 'flex';
}
alertClose.addEventListener('click', () => {
    alertModal.style.display = 'none';
});

// --- NEW: Refactored initialization logic ---
/**
 * Resets the entire labyrinth to a new, blank state with the given dimensions.
 * @param {number} newWidth - The new labyrinth width.
 * @param {number} newHeight - The new labyrinth height.
 */
function resetLabyrinth(newWidth, newHeight) {
    LABYRINTH_WIDTH = newWidth;
    LABYRINTH_HEIGHT = newHeight;

    // Update canvas physical and logical size
    canvas.width = LABYRINTH_WIDTH;
    canvas.height = LABYRINTH_HEIGHT;

    // Re-initialize the grid (all walls)
    grid = new Array(LABYRINTH_HEIGHT).fill(0).map(() => 
        new Array(LABYRINTH_WIDTH).fill(1)
    );

    // Re-create the image data buffer for the new size
    imageData = ctx.createImageData(LABYRINTH_WIDTH, LABYRINTH_HEIGHT);

    // Clear all objects
    robots = [];
    beacons = [];
    areas = []; 

    // Update resize modal placeholders
    resizeWidth.value = LABYRINTH_WIDTH;
    resizeHeight.value = LABYRINTH_HEIGHT;
    
    // Draw the new blank state
    redrawAll();
}

// --- Core Functions ---

function applyBrush(mouseX, mouseY) {
    const radius = brushRadius;
    const radiusSq = radius * radius; 

    const startX = Math.max(0, Math.floor(mouseX - radius));
    const endX = Math.min(LABYRINTH_WIDTH, Math.ceil(mouseX + radius));
    const startY = Math.max(0, Math.floor(mouseY - radius));
    const endY = Math.min(LABYRINTH_HEIGHT, Math.ceil(mouseY + radius));

    const toolValue = parseInt(toolMode.value, 10);

    for (let y = startY; y < endY; y++) {
        for (let x = startX; x < endX; x++) {
            const dx = x - mouseX;
            const dy = y - mouseY;
            
            if (dx * dx + dy * dy <= radiusSq) {
                // Bounds check is implicit in loop, but good to have
                if (y >= 0 && y < LABYRINTH_HEIGHT && x >= 0 && x < LABYRINTH_WIDTH) {
                    grid[y][x] = toolValue; // 0 for path, 1 for wall
                }
            }
        }
    }
}

function drawGrid() {
    // Ensure grid and imageData exist
    if (!grid || !imageData) return;

    const data = imageData.data;
    for (let y = 0; y < LABYRINTH_HEIGHT; y++) {
        for (let x = 0; x < LABYRINTH_WIDTH; x++) {
            const index = (y * LABYRINTH_WIDTH + x) * 4;
            const color = (grid[y][x] === 1) ? WALL_COLOR : PATH_COLOR;
            
            data[index]     = color[0]; // R
            data[index + 1] = color[1]; // G
            data[index + 2] = color[2]; // B
            data[index + 3] = color[3]; // A
        }
    }
    ctx.putImageData(imageData, 0, 0);
}

function drawObjects() {
    if (!robots || !beacons || !areas) return;

    // Draw Areas FIRST (so they are in the background)
    areas.forEach(area => {
        ctx.save();
        ctx.fillStyle = area.color;
        ctx.strokeStyle = area.color;
        
        // Draw semi-transparent fill
        ctx.globalAlpha = 0.2;
        ctx.beginPath();
        ctx.arc(area.x, area.y, area.radius, 0, 2 * Math.PI);
        ctx.fill();
        
        // Draw a more solid border
        ctx.globalAlpha = 0.8;
        ctx.lineWidth = 2;
        ctx.stroke();
        
        ctx.restore(); // Resets globalAlpha
        
        // Draw name
        ctx.fillStyle = area.color;
        ctx.font = '10px sans-serif';
        ctx.textAlign = 'left';
        ctx.fillText(area.name, area.x + area.radius + 3, area.y + 4);
    });

    // Draw Robots
    robots.forEach(robot => {
        ctx.save();
        // Translate and rotate for direction
        ctx.translate(robot.x, robot.y);
        // Use radian value directly
        ctx.rotate(robot.angle || 0); 

        // Draw robot body (at new 0,0)
        ctx.beginPath();
        ctx.arc(0, 0, ROBOT_RADIUS, 0, 2 * Math.PI);
        ctx.fillStyle = robot.color;
        ctx.fill();
        ctx.strokeStyle = '#FFFFFF'; 
        ctx.lineWidth = 1; 
        ctx.stroke();

        // Draw direction pointer
        ctx.beginPath();
        ctx.moveTo(0, 0);
        ctx.lineTo(ROBOT_RADIUS + 3, 0);
        ctx.strokeStyle = '#FFFFFF';
        ctx.lineWidth = 2;
        ctx.stroke();
        
        ctx.restore(); // Restore context to default

        // Draw name (at original x,y)
        ctx.fillStyle = robot.color; 
        ctx.font = '10px sans-serif';
        ctx.textAlign = 'left';
        ctx.fillText(robot.name, robot.x + ROBOT_RADIUS + 3, robot.y + 4);
    });

    // Draw Beacons
    beacons.forEach(beacon => {
        ctx.strokeStyle = BEACON_COLOR;
        ctx.lineWidth = 2;
        
        ctx.beginPath();
        ctx.moveTo(beacon.x - BEACON_SIZE, beacon.y - BEACON_SIZE);
        ctx.lineTo(beacon.x + BEACON_SIZE, beacon.y + BEACON_SIZE);
        ctx.moveTo(beacon.x + BEACON_SIZE, beacon.y - BEACON_SIZE);
        ctx.lineTo(beacon.x - BEACON_SIZE, beacon.y + BEACON_SIZE);
        ctx.stroke();

        ctx.fillStyle = BEACON_COLOR; 
        ctx.font = '10px sans-serif';
        ctx.textAlign = 'left';
        ctx.fillText(beacon.name, beacon.x + BEACON_SIZE + 3, beacon.y + 4);
    });
}

function redrawAll() {
    drawGrid();
    drawObjects();
}

function handleDraw(event) {
    if (!isDrawing) return;
    if (currentTool > 1) return; // Only for carving/building

    const rect = canvas.getBoundingClientRect();
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;
    const mouseX = (event.clientX - rect.left) * scaleX;
    const mouseY = (event.clientY - rect.top) * scaleY;

    applyBrush(mouseX, mouseY);
    redrawAll(); 
}

// Find if a click hit an object
function findClickedObject(x, y) {
    // Check robots first (reverse loop to hit top ones)
    for (let i = robots.length - 1; i >= 0; i--) {
        const robot = robots[i];
        const dx = x - robot.x;
        const dy = y - robot.y;
        if (dx * dx + dy * dy <= ROBOT_RADIUS * ROBOT_RADIUS) {
            return { type: 'robot', index: i };
        }
    }
    // Check beacons
    for (let i = beacons.length - 1; i >= 0; i--) {
        const beacon = beacons[i];
        if (x >= beacon.x - BEACON_SIZE && x <= beacon.x + BEACON_SIZE &&
            y >= beacon.y - BEACON_SIZE && y <= beacon.y + BEACON_SIZE) {
            return { type: 'beacon', index: i };
        }
    }
    // Check areas (last, so small objects on top are clickable)
    for (let i = areas.length - 1; i >= 0; i--) {
        const area = areas[i];
        const dx = x - area.x;
        const dy = y - area.y;
        if (dx * dx + dy * dy <= area.radius * area.radius) {
            return { type: 'area', index: i };
        }
    }
    return null; // No object hit
}

let beacons_placed = 0;
// Now places object AND opens edit panel
function handlePlaceObject(mouseX, mouseY) {
    let newIndex = -1;
    let newType = null;

    if (currentTool === 2) { // Place Robot
        const newRobot = { x: mouseX, y: mouseY, name: "Anon", color: "#BBBBBB", angle: 0 };
        newIndex = robots.push(newRobot) - 1;
        newType = 'robot';
    } else if (currentTool === 3) { // Place Beacon
        beacons_placed += 1;
        const newBeacon = { x: mouseX, y: mouseY, name: "B" + beacons_placed };
        newIndex = beacons.push(newBeacon) - 1;
        newType = 'beacon';
    } else if (currentTool === 4) { // Place Area
        const newArea = { 
            x: mouseX, 
            y: mouseY, 
            name: "Area", 
            color: DEFAULT_AREA_COLOR, 
            radius: 50,
            victory_robots: [], // Default empty array
            on_beacon: "",      // Default empty string
            off_beacon: "",     // Default empty string
            sticky_switch: false, // Default false
            // --- *** 2. ADDED IMPENETRABLE DEFAULT *** ---
            impenetrable: false
        };
        newIndex = areas.push(newArea) - 1;
        newType = 'area';
    }
    
    redrawAll(); // Re-draw to show the new object

    // Open edit panel for the object we just created
    if (newIndex !== -1 && newType) {
        openEditPanel(newType, newIndex);
    }
}

// Helper to populate beacon dropdowns
function populateBeaconDropdowns(selectedOnBeacon = '', selectedOffBeacon = '') {
    // Clear existing options
    editOnBeacon.innerHTML = '<option value="">-- None --</option>';
    editOffBeacon.innerHTML = '<option value="">-- None --</option>';

    // Add all existing beacons
    beacons.forEach(b => {
        const optionOn = document.createElement('option');
        optionOn.value = b.name;
        optionOn.textContent = b.name;
        editOnBeacon.appendChild(optionOn);

        const optionOff = document.createElement('option');
        optionOff.value = b.name;
        optionOff.textContent = b.name;
        editOffBeacon.appendChild(optionOff);
    });

    // Set selected values
    editOnBeacon.value = selectedOnBeacon;
    editOffBeacon.value = selectedOffBeacon;
}

// Handles all object types
function openEditPanel(type, index) {
    selectedObjectType = type;
    selectedObjectIndex = index;
    
    // Hide all optional rows by default
    editColorRow.style.display = 'none';
    editAngleRow.style.display = 'none';
    angleEditorRow.style.display = 'none';
    editRadiusRow.style.display = 'none';
    editVictoryRobotsRow.style.display = 'none';
    editOnBeaconRow.style.display = 'none';
    editOffBeaconRow.style.display = 'none';
    editStickySwitchRow.style.display = 'none';
    // --- *** 3. HIDE IMPENETRABLE ROW BY DEFAULT *** ---
    editImpenetrableRow.style.display = 'none';
    
    if (type === 'robot') {
        const obj = robots[index];
        const angleDeg = (obj.angle || 0) * 180 / Math.PI;
        editTitle.textContent = "Edit Robot";
        editName.value = obj.name;
        editColor.value = obj.color;
        editAngle.value = Math.round(angleDeg);
        // Show relevant rows
        editColorRow.style.display = 'flex';
        editAngleRow.style.display = 'flex';
        angleEditorRow.style.display = 'flex';
        drawAngleEditor(angleDeg);
    } else if (type === 'beacon') {
        const obj = beacons[index];
        editTitle.textContent = "Edit Beacon";
        editName.value = obj.name;
        // All optional rows remain hidden
    } else if (type === 'area') {
        const obj = areas[index];
        editTitle.textContent = "Edit Area";
        editName.value = obj.name;
        editColor.value = obj.color;
        editRadius.value = obj.radius;
        // Parse array to comma-separated string for display
        editVictoryRobots.value = obj.victory_robots ? obj.victory_robots.join(', ') : '';
        editStickySwitch.checked = obj.sticky_switch;
        // --- *** 3. SET CHECKBOX STATE *** ---
        editImpenetrable.checked = obj.impenetrable;

        // Populate beacon dropdowns for 'on_beacon' and 'off_beacon'
        populateBeaconDropdowns(obj.on_beacon, obj.off_beacon);

        // Show relevant rows for Area
        editColorRow.style.display = 'flex';
        editRadiusRow.style.display = 'flex';
        editVictoryRobotsRow.style.display = 'flex';
        editOnBeaconRow.style.display = 'flex';
        editOffBeaconRow.style.display = 'flex';
        editStickySwitchRow.style.display = 'flex';
        // --- *** 3. SHOW IMPENETRABLE ROW *** ---
        editImpenetrableRow.style.display = 'flex';
    }
    editModal.style.display = 'flex'; // Show the modal
}

// Function to draw the angle editor dial
function drawAngleEditor(angleDeg) {
    const size = angleEditor.width;
    const centerX = size / 2;
    const centerY = size / 2;
    const radius = size / 2 - 5; // A bit smaller to allow for stroke

    angleEditorCtx.clearRect(0, 0, size, size);

    // Draw the outer circle
    angleEditorCtx.beginPath();
    angleEditorCtx.arc(centerX, centerY, radius, 0, 2 * Math.PI);
    angleEditorCtx.strokeStyle = '#666';
    angleEditorCtx.lineWidth = 2;
    angleEditorCtx.stroke();

    // Draw the current angle pointer
    angleEditorCtx.save();
    angleEditorCtx.translate(centerX, centerY);
    // Convert degrees to radians for drawing
    const angleRad = angleDeg * Math.PI / 180;
    angleEditorCtx.rotate(angleRad);
    
    angleEditorCtx.beginPath();
    angleEditorCtx.moveTo(0, 0);
    angleEditorCtx.lineTo(radius, 0);
    angleEditorCtx.strokeStyle = '#007aff';
    angleEditorCtx.lineWidth = 3;
    angleEditorCtx.stroke();
    
    // Draw a small circle at the end of the pointer
    angleEditorCtx.beginPath();
    angleEditorCtx.arc(radius, 0, 4, 0, 2 * Math.PI);
    angleEditorCtx.fillStyle = '#007aff';
    angleEditorCtx.fill();

    angleEditorCtx.restore();
}

// Event handler for mouse down on angle editor
function startAngleDrag(e) {
    if (selectedObjectType === 'robot' && angleEditorRow.style.display === 'flex') {
        isDraggingAngle = true;
        updateAngleFromMouse(e);
    }
}

// Event handler for mouse move on angle editor
function updateAngleDrag(e) {
    if (isDraggingAngle) {
        updateAngleFromMouse(e);
    }
}

// Event handler for mouse up on angle editor
function stopAngleDrag() {
    isDraggingAngle = false;
}

// Helper to calculate angle from mouse position
function updateAngleFromMouse(e) {
    const rect = angleEditor.getBoundingClientRect();
    const centerX = rect.left + rect.width / 2;
    const centerY = rect.top + rect.height / 2;

    const mouseX = e.clientX;
    const mouseY = e.clientY;

    const dx = mouseX - centerX;
    const dy = mouseY - centerY;

    let angleRad = Math.atan2(dy, dx); // Angle from +X axis
    let angleDeg = angleRad * 180 / Math.PI;

    angleDeg = (angleDeg + 360) % 360; // Keep between 0-360

    editAngle.value = Math.round(angleDeg);
    drawAngleEditor(angleDeg);
}

function saveObjectChanges() {
    if (selectedObjectIndex === -1 || !selectedObjectType) {
        customAlert("No object selected for saving.");
        return;
    }

    const newName = editName.value.trim();
    if (!newName) {
        customAlert("Name cannot be empty.");
        return;
    }

    // Check for name uniqueness
    let nameConflict = false;
    if (selectedObjectType === 'robot') {
        nameConflict = robots.some((r, i) => i !== selectedObjectIndex && r.name === newName);
    } else if (selectedObjectType === 'beacon') {
        nameConflict = beacons.some((b, i) => i !== selectedObjectIndex && b.name === newName);
    } else if (selectedObjectType === 'area') {
        nameConflict = areas.some((a, i) => i !== selectedObjectIndex && a.name === newName);
    }

    if (nameConflict) {
        customAlert(`An object with the name "${newName}" already exists. Please choose a unique name.`);
        return;
    }

    if (selectedObjectType === 'robot') {
        const robot = robots[selectedObjectIndex];
        robot.name = newName;
        robot.color = editColor.value;
        robot.angle = parseInt(editAngle.value, 10) * Math.PI / 180;
    } else if (selectedObjectType === 'beacon') {
        const beacon = beacons[selectedObjectIndex];
        beacon.name = newName;
    } else if (selectedObjectType === 'area') {
        const area = areas[selectedObjectIndex];
        area.name = newName;
        area.color = editColor.value;
        area.radius = parseInt(editRadius.value, 10);
        // Parse comma-separated string back to array for victory_robots
        area.victory_robots = editVictoryRobots.value.split(',').map(s => s.trim()).filter(s => s !== '');
        area.on_beacon = editOnBeacon.value;
        area.off_beacon = editOffBeacon.value;
        area.sticky_switch = editStickySwitch.checked;
        // --- *** 4. SAVE IMPENETRABLE STATE *** ---
        area.impenetrable = editImpenetrable.checked;
    }

    editModal.style.display = 'none';
    redrawAll();
}

function deleteObject() {
    if (selectedObjectIndex === -1 || !selectedObjectType) {
        customAlert("No object selected for deletion.");
        return;
    }

    if (selectedObjectType === 'robot') {
        robots.splice(selectedObjectIndex, 1);
    } else if (selectedObjectType === 'beacon') {
        beacons.splice(selectedObjectIndex, 1);
        // If a beacon is deleted, clear its reference from any areas
        const deletedBeaconName = editName.value; // Get the name before deletion
        areas.forEach(area => {
            if (area.on_beacon === deletedBeaconName) area.on_beacon = "";
            if (area.off_beacon === deletedBeaconName) area.off_beacon = "";
        });
    } else if (selectedObjectType === 'area') {
        areas.splice(selectedObjectIndex, 1);
    }

    selectedObjectIndex = -1;
    selectedObjectType = null;
    editModal.style.display = 'none';
    redrawAll();
}

// --- File Operations ---

downloadButton.addEventListener('click', () => {
    // Generate walls string
    let wallsString = '';
    for (let y = 0; y < LABYRINTH_HEIGHT; y++) {
        for (let x = 0; x < LABYRINTH_WIDTH; x++) {
            wallsString += grid[y][x];
        }
    }

    // Filter out temporary beacon/area properties for export if not needed in simulator
    const robotsExport = robots.map(r => ({
        x: r.x, y: r.y, name: r.name, color: r.color, angle: r.angle
    }));
    const beaconsExport = beacons.map(b => ({
        x: b.x, y: b.y, name: b.name
    }));
    const areasExport = areas.map(a => ({
        x: a.x, y: a.y, name: a.name, color: a.color, radius: a.radius,
        victory_robots: a.victory_robots,
        on_beacon: a.on_beacon,
        off_beacon: a.off_beacon,
        sticky_switch: a.sticky_switch,
        // --- *** 5. EXPORT IMPENETRABLE STATE *** ---
        impenetrable: a.impenetrable
    }));


    const data = {
        width: LABYRINTH_WIDTH,
        height: LABYRINTH_HEIGHT,
        walls: wallsString,
        robots: robotsExport,
        beacons: beaconsExport,
        areas: areasExport
    };

    const filename = 'labyrinth.json';
    const jsonStr = JSON.stringify(data, null, 2);
    
    const blob = new Blob([jsonStr], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
});

loadButton.addEventListener('click', () => fileInput.click());
fileInput.addEventListener('change', (event) => {
    const file = event.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (e) => {
        try {
            const data = JSON.parse(e.target.result);
            
            const newWidth = data.width || 500;
            const newHeight = data.height || 500;
            resetLabyrinth(newWidth, newHeight); // Reset with new dimensions

            // Load walls
            const wallsString = data.walls;
            if (wallsString) {
                for (let y = 0; y < LABYRINTH_HEIGHT; y++) {
                    for (let x = 0; x < LABYRINTH_WIDTH; x++) {
                        const val = parseInt(wallsString[y * LABYRINTH_WIDTH + x], 10);
                        grid[y][x] = isNaN(val) ? 1 : val; // Default to wall if invalid
                    }
                }
            }

            // Load robots
            robots = data.robots || [];
            // Ensure angles are numbers (sometimes load as strings from JSON)
            robots.forEach(r => r.angle = parseFloat(r.angle || 0));

            // Load beacons
            beacons = data.beacons || [];

            // Load areas
            areas = data.areas || [];
            // Ensure new properties have defaults if not present in old files
            areas.forEach(a => {
                a.color = a.color || DEFAULT_AREA_COLOR;
                a.radius = a.radius || 50;
                a.victory_robots = a.victory_robots || [];
                a.on_beacon = a.on_beacon || "";
                a.off_beacon = a.off_beacon || "";
                a.sticky_switch = a.sticky_switch === true; // Ensure boolean
                // --- *** 6. LOAD IMPENETRABLE (defaulting to false) *** ---
                a.impenetrable = a.impenetrable === true; // Ensure boolean
            });

            redrawAll();
            customAlert('Labyrinth loaded successfully!');
        } catch (error) {
            console.error('Failed to parse JSON file:', error);
            customAlert('Failed to load labyrinth: ' + error.message);
        }
    };
    reader.readAsText(file);
    event.target.value = null; // Clear file input
});

// --- Event Listeners ---
canvas.addEventListener('mousedown', (e) => {
    const rect = canvas.getBoundingClientRect();
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;
    const mouseX = (e.clientX - rect.left) * scaleX;
    const mouseY = (e.clientY - rect.top) * scaleY;

    if (currentTool <= 1) { // Carving or Building
        isDrawing = true;
        applyBrush(mouseX, mouseY);
        redrawAll();
    } else if (currentTool >= 2 && currentTool <= 4) { // Place Object (Robot, Beacon, Area)
        handlePlaceObject(mouseX, mouseY);
    } else if (currentTool === 5) { // Selection / Edit
        const clicked = findClickedObject(mouseX, mouseY);
        if (clicked) {
            openEditPanel(clicked.type, clicked.index);
        }
    }
});

canvas.addEventListener('mousemove', handleDraw);
canvas.addEventListener('mouseup', () => {
    isDrawing = false;
});
canvas.addEventListener('mouseleave', () => {
    isDrawing = false;
});

brushSlider.addEventListener('input', (e) => {
    brushRadius = parseInt(e.target.value, 10);
});

toolMode.addEventListener('change', (e) => {
    currentTool = parseInt(e.target.value, 10);
    canvas.style.cursor = (currentTool <= 1) ? 'crosshair' : 'default';
});

// Edit Modal Buttons
saveEdit.addEventListener('click', saveObjectChanges);
deleteEdit.addEventListener('click', deleteObject);
closeEdit.addEventListener('click', () => {
    editModal.style.display = 'none';
    selectedObjectIndex = -1;
    selectedObjectType = null;
    redrawAll(); // Redraw in case object was moved/deleted
});

// Angle Editor events
angleEditor.addEventListener('mousedown', startAngleDrag);
angleEditor.addEventListener('mousemove', updateAngleDrag);
angleEditor.addEventListener('mouseup', stopAngleDrag);
angleEditor.addEventListener('mouseleave', stopAngleDrag);
editAngle.addEventListener('input', (e) => {
    const angleDeg = parseFloat(e.target.value);
    if (!isNaN(angleDeg)) {
        drawAngleEditor(angleDeg);
    }
});


// Resize Modal Buttons
resizeButton.addEventListener('click', () => {
    resizeWidth.value = LABYRINTH_WIDTH;
    resizeHeight.value = LABYRINTH_HEIGHT;
    resizeModal.style.display = 'flex';
});
cancelResize.addEventListener('click', () => {
    resizeModal.style.display = 'none';
});
applyResize.addEventListener('click', () => {
    const newWidth = parseInt(resizeWidth.value, 10);
    const newHeight = parseInt(resizeHeight.value, 10);
    if (isNaN(newWidth) || isNaN(newHeight) || newWidth < 10 || newHeight < 10) {
        customAlert("Please enter valid width and height (min 10).");
        return;
    }
    resetLabyrinth(newWidth, newHeight);
    resizeModal.style.display = 'none';
});


// --- Initial setup ---
resetLabyrinth(LABYRINTH_WIDTH, LABYRINTH_HEIGHT); // Initialize a default empty labyrinth