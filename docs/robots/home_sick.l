
HomeSick(x, i_am_home) = (if i_am_home then 0 else x);

WeightedAverage(k->v) = Sum(k * v) / Sum(k);
# Steer toward open space
FreedomMotion(radar) = WeightedAverage{
  x.distance -> x.angle :- x in radar
};
Robot(robot_name:, desire:, memory: "I am") :-
  Sensor(robot_name:, sensor:),
  freedom = FreedomMotion(sensor.radar),
  i_am_home = !~ (x in sensor.radar, x.label == "Home", x.distance < 40),
  speed = 0.7,
  desire = {
    left_engine: HomeSick(speed + 0.1 - freedom, i_am_home),
    right_engine: HomeSick(speed + freedom, i_am_home)
  };

