Love(radar, robot_name) = Coalesce(
  1{ x.angle  :- x in radar, x.object = "robot", x.distance > 20},
  0.2
);

Q(robot_name) = Love(sensor.radar) :-
  Sensor(robot_name:, sensor:);
  

Robot(robot_name:, desire:, memory: "I am") :-
  Sensor(robot_name:, sensor:),
  speed = 0.4,
  desire = {
    left_engine: speed, 
    right_engine: speed + Love(sensor.radar, robot_name)
  };
