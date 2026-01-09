# ==========================================
# Helper Functions & State Management
# ==========================================

DefaultMem() = {
  mode: "search",
  monitor: "System Initialized"
};

CastOr(x, y) = Coalesce(TryCast(x, y), y);

# Parse memory from the database, casting to default if missing
@Ground(ParsedMem);
ParsedMem(robot_name) = CastOr(memory, DefaultMem()) :-
  Memory(robot_name:, memory:);

State(robot_name) = ParsedMem(robot_name);

NewState(robot_name) = state :-
  state = State(robot_name);

# Sensor Helpers
Take(x) = Coalesce(ArgMin(x -> x.distance), {angle: 0, distance: 200, object: "nothing", label: "nothing"});
L(radar) = Take{ x :- x in radar, x.label == "L" };
R(radar) = Take{ x :- x in radar, x.label == "R" };
Wall(radar) = Coalesce(Min{x.distance :- x in radar, x.object == "wall"}, 200);


# ==========================================
# Main Logic: Search & Align Mode
# ==========================================
Robot(robot_name:,
      desire: {
        left_engine: left_engine,
        right_engine: right_engine
      },
      memory: {
        mode: next_mode,
        monitor: "L=" ++ ToString(l) ++
                 ", R=" ++ ToString(r) ++
                 ", b_d=" ++ ToString(bias_dist) ++
                 ", speed=" ++ ToString(speed)
      }) :-
  # 1. Inputs
  Sensor(robot_name:, sensor:),
  state = NewState(robot_name),
  state.mode == "search",

  # 2. Perception
  l = L(sensor.radar),
  r = R(sensor.radar),
  wall_dist = Wall(sensor.radar),
  
  # 3. Control Logic Calculations
  desired_distance = 120 + 70 * Sin(sensor.clock / 100),
  
  # bias_dist: Difference in distance between Left and Right targets
  bias_dist = 2 * (
    if l.distance < 190 && r.distance < 190 then
      (l.distance - r.distance) / 100
    else 0
  ),

  # speed: Base forward/backward velocity based on target distance
  speed = (
    if l.object == "nothing" && r.object == "nothing" then 0.6
    else if l.distance > desired_distance + 15      then 0.5
    else if l.distance < desired_distance - 15      then -0.5
    else 0
  ),
  
  speed_sign = (if speed > 0 then 1 else -1),

  # wall_avoidance: Steer away if wall is close
  wall_avoidance = 0.2 * (
    if l.object == "nothing" && r.object == "nothing" then
      Least(30, Greatest(0, (100 - wall_dist) / 100))
    else 0
  ),

  # search_bias: Slight drift to help scan if nothing is seen
  search_bias = (if l.object == "nothing" && r.object == "nothing" then 0.1 else 0.0),
  
  omega = 0.1, # Turning coefficient

  # 4. Engine Output Calculation
  # Differential steering formula
  left_engine  = speed - omega * (l.angle + r.angle + speed_sign * bias_dist) + wall_avoidance,
  right_engine = speed + omega * (l.angle + r.angle + speed_sign * bias_dist) - wall_avoidance + search_bias,

  # 5. State Transition Logic
  next_mode = (
    if l.object == "nothing" && r.object == "nothing" then "search"
    else if Abs(bias_dist) > 0.05                     then "search" # Not centered yet
    else if l.distance > 150 || r.distance > 150      then "search" # Too far away
    else if Abs(l.angle + r.angle) > 0.02             then "search" # Not facing correctly
    else "forward"                                                  # Ready to charge!
  );


# ==========================================
# Main Logic: Forward / Charge Mode
# ==========================================
Robot(robot_name:,
      desire: {left_engine: 1.0, right_engine: 1.0},
      memory: {mode: next_mode, monitor: state.monitor}) :-
  Sensor(robot_name:, sensor:),
  state = NewState(robot_name),
  state.mode == "forward",
  
  # Keep charging until obstacle is within 50 units
  next_mode = (
    if sensor.forward_distance > 50 then "forward"
    else "search"
  );