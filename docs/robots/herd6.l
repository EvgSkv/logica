

WeightedAverage(k->v) = Sum(k * v) / Sum(k);
# Steer toward open space
FreedomMotion(radar) = WeightedAverage{
  x.distance * m -> x.angle + d :-
  x in radar,
  m = (if x.object == "robot" then 30.0 else 1.0),
  d = (if x.object == "robot" then 0.01 else 0.0)
};

SeeBrother(radar) = Coalesce(AnyValue{true :- x.object == "robot", x in radar}, false);

ParseWithDefault(s, d) = Coalesce(TryCast(s, d), d);

@Ground(ParsedMemory);
ParsedMemory(robot_name) = ParseWithDefault(memory, {loneliness: 100}) :-
  Memory(robot_name:, memory:);

NewMemory(robot_name) = {loneliness:} :-
  mem = ParsedMemory(robot_name),
  loneliness = (
    if SeeBrother(sensor.radar) then
      0
    else
      mem.loneliness + 1
  ),
  Sensor(robot_name:, sensor:);

Robot(robot_name:, desire:, memory:) :-
  Sensor(robot_name:, sensor:),
  memory = NewMemory(robot_name),
  radar = sensor.radar,
  freedom = FreedomMotion(radar),
  personal_boundary = (if robot_name == "Hamlet" then 0 else 20),
  speed_freedom = (Least(80, sensor.forward_distance) - personal_boundary) / 100,
  brother_boost = (if SeeBrother(radar) then 0.2 else 0),
  loneliness_spin = (if robot_name != "Hamlet" && memory.loneliness < 50 then 0.4 else 0),
  speed = speed_freedom + brother_boost,
  desire = {
    left_engine: speed - freedom - (if SeeBrother(radar) then 0.5 else 0.02) + loneliness_spin,
    right_engine: speed + freedom - loneliness_spin
  };

