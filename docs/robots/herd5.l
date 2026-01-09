

WeightedAverage(k->v) = Sum(k * v) / Sum(k);
# Steer toward open space
FreedomMotion(radar) = WeightedAverage{
  x.distance * m -> x.angle + d :-
  x in radar,
  m = (if x.object == "robot" then 30.0 else 1.0),
  d = (if x.object == "robot" then 0.01 else 0.0)
};

SeeBrother(radar) = Coalesce(AnyValue{true :- x.object == "robot", x in radar}, false);

Robot(robot_name:, desire:, memory: "I am") :-
  Sensor(robot_name:, sensor:),
  radar = sensor.radar,
  freedom = FreedomMotion(radar),
  speed_freedom = (Least(80, sensor.forward_distance) - 20) / 100,
  brother_boost = (if SeeBrother(radar) then 0.4 else 0),
  speed = speed_freedom + brother_boost,
  desire = {
    left_engine: speed - freedom - (if SeeBrother(radar) then 0 else 0.02),
    right_engine: speed + freedom
  };

