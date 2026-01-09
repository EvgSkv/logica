

WeightedAverage(k->v) = Sum(k * v) / Sum(k);
# Steer toward open space
FreedomMotion(radar) = WeightedAverage{
  x.distance -> x.angle :- x in radar
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
    left_engine: speed - freedom + 0.1,
    right_engine: speed + freedom
  };

