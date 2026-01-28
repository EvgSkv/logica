DefaultMem() = {mode: "search", monitor: "Nothing on monitor"};

@Ground(ParsedMem);
ParsedMem(robot_name) = TryCast(memory, DefaultMem()) :-
  Memory(robot_name:, memory:);

State(robot_name) =  Coalesce(ParsedMem(robot_name), DefaultMem());

NewState(robot_name) = state :-
  state = State(robot_name);


Take(x) = Coalesce(ArgMin(x -> x.distance), {angle: 0, distance: 200, object: "nothing", label: "nothing"});

L(radar) = Take{ x :- x in radar, x.label == "L" };
R(radar) = Take{ x :- x in radar, x.label == "R" };
Wall(radar) = Coalesce( Min{x.distance :- x in radar, x.object = "wall"}, 200 );

Robot(robot_name:,
      desire: {
        left_engine:,
        right_engine:
      },
      memory: {mode:, monitor: "l = " ++ ToString(l) ++ ", r = " ++ ToString(r) ++ ", b_d = " ++ ToString(b_d) ++ ",speed= " ++ ToString(speed) ++ ", speed_sign=" ++ ToString(speed_sign) ++ ", defacto_speed=" ++ ToString(left_engine + right_engine)}) :-
  # Read memory if needed:
  # Memory(robot_name:, memory: old_memory),  
  memory = ("I, " ++ robot_name ++", desire and therefore I am. I see " ++
            sensor.forward_object ++ " is at " ++ ToString(sensor.forward_distance)),
  state = NewState(robot_name),
  l = L(sensor.radar),
  r = R(sensor.radar),
  l_a = l.angle,
  r_a = r.angle,
  b_d = 2 * (
    if l.distance < 190 && r.distance < 190 then
      (l.distance - r.distance) / 100
    else
      0
  ),
  bias = (
    if l.object == "nothing" && r.object == "nothing" then
      0.1
    else
      0.0
  ),
  avoid = 0.2 * (
    if l.object == "nothing" && r.object == "nothing" then
      Least(30, Greatest(0, (100 - d) / 100))
    else
      0
  ),
  speed = (
    if l.object == "nothing" && r.object == "nothing" then
      0.6
    else if l.distance > desired_distance + 15 then
      0.5
    else if l.distance < desired_distance - 15 then
      -0.5
    else
      0
  ),
  speed_sign = (
    if speed > 0 then
      1
    else
      -1
  ),
  desired_distance = 120 + 70 * Sin(sensor.clock / 200),
  d = Wall(sensor.radar),
  omega = 0.1,
  Sensor(robot_name:, sensor:),
  left_engine = speed  - omega * (l_a + r_a + speed_sign * b_d) + avoid,
  right_engine = speed + omega * (l_a + r_a + speed_sign * b_d) -avoid + bias,
  state.mode == "search",
  mode = (
    if l.object == "nothing" && r.object == "nothing" then
      "search"
    else if Abs(b_d) > 0.05 then
      "search"
    else if l.distance > 150 || r.distance > 150 then
      "search"
    else if l_a + r_a > 0.02 then
      "search"
    else
      "forward"
  );

Robot(robot_name:,
      desire: {left_engine: 1.0, right_engine: 1.0},
      memory: {mode:, monitor: state.monitor}) :-
  state = NewState(robot_name),
  Sensor(robot_name:, sensor:),
  state.mode == "forward",
  mode = (
    if sensor.forward_distance > 50 then
      "forward"
    else
      "search"
  );