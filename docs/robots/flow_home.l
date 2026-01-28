
WeightedAverage(k->v) = Sum(k * v) / Sum(k);
# Steer toward open space
FreedomMotion(radar) = WeightedAverage{
  x.distance -> x.angle :- x in radar
};

SeeHome(radar) = !~ (x in radar, x.label == "Home", x.distance < 50);

Robot(robot_name:, desire:, memory: "I am") :-
  Sensor(robot_name:, sensor:),
  freedom = FreedomMotion(sensor.radar),
  speed = 0.5,
  search_desire = {
    left_engine: speed - freedom + 0.1,
    right_engine: speed + freedom
  },
  desire = (if SeeHome(sensor.radar) then {left_engine: 0, right_engine: 0} else search_desire);

RobotHome(robot_name) = SeeHome(sensor.radar) :-
  Sensor(robot_name:, sensor:);
