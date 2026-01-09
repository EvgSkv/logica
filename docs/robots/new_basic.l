

WeightedAverage(k->v) = Sum(k * v) / Sum(k);
# Steer toward open space
FreedomMotion(radar) = WeightedAverage{
  x.distance -> x.angle :- x in radar
};
Robot(robot_name:, desire:, memory: "I am") :-
  Sensor(robot_name:, sensor:),
  freedom = FreedomMotion(sensor.radar),
  speed = (if sensor.forward_distance > 20 then 0.5 else -0.1),
  desire = {
    left_engine: speed - freedom + 0.1,
    right_engine: speed + freedom
  };

