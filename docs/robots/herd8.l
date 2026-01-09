
WeightedAverage(k->v) = Sum(k * v) / Sum(k);
# Steer toward open space
FreedomMotion(radar) = WeightedAverage{
  x.distance * spirit -> x.angle :-
  x in radar,
  spirit = (if x.object == "robot" then 30.0 else 1.0)
};

SeeCompany(radar) = !~ (x in radar, x.object == "robot");

ParseWithDefault(s, d) = Coalesce(TryCast(s, d), d);

@Ground(ParsedMemory);
ParsedMemory(robot_name) = ParseWithDefault(memory, {loneliness: 100}) :-
  Memory(robot_name:, memory:);

NewMemory(robot_name) = {loneliness:} :-
  mem = ParsedMemory(robot_name),
  loneliness = (
    if SeeCompany(sensor.radar) then
      0
    else
      mem.loneliness + 1
  ),
  Sensor(robot_name:, sensor:);

@Ground(Leader);
Leader() = Min{robot_name :- Sensor(robot_name:)};

Robot(robot_name:, desire:, memory:) :-
  Sensor(robot_name:, sensor:),
  memory = NewMemory(robot_name),
  radar = sensor.radar,
  freedom = FreedomMotion(radar),
  left_bias = Sin(sensor.clock / 1000) * 0.03,
  speed_freedom = (Least(80, sensor.forward_distance) - 20) / 100,
  company_boost = (if SeeCompany(radar) then 0.5 else 0),
  loneliness_spin = (
    if robot_name == Leader() then
      0  # Leader is stoic.
    else if memory.loneliness > 100 then
      0  # You get used to loneliness.
    else if memory.loneliness == 0 then
      0  # Not lonely!
    else
      0.4  # Look for social connection!
  ),
  speed = speed_freedom + company_boost,
  desire = {
    left_engine: speed - freedom - left_bias + loneliness_spin,
    right_engine: speed + freedom - loneliness_spin
  };
  
