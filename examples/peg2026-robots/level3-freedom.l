WeightedAverage(k->v) = Sum(k * v) / Sum(k);
# Steer toward open space
FreedomMotion(radar) = WeightedAverage{
  x.distance -> x.angle :- x in radar
};
Robot(robot_name:, desire:, memory: "I am") :-
  Sensor(robot_name:, sensor:),
  freedom = FreedomMotion(sensor.radar),
  speed = 0.5,
  desire = {
    left_engine: speed - freedom + 0.1,
    right_engine: speed + freedom
  };

