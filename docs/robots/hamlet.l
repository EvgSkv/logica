@Ground(RobotIndex);
RobotIndex(robot_name) = i :-
  i in Range(Size(robots)),
  robot_name = robots[i],
  robots = Array{ t -> t :- Sensor(robot_name: t)};

Hamlet(n) = (RobotIndex(n) == 0);

I(x) = ToFloat64(x);
Robot(robot_name:,
      desire: {
        left_engine: left_engine - hamlet_angle + boost,
        right_engine: right_engine + hamlet_angle + boost
      },
      memory: robot_name ++ ToString(hamlet_angle)) :-
  Memory(robot_name:, memory: old_memory),  
  # Just pass memory forward, or reset to remember Earth.
  memory = Coalesce(old_memory, "Earth"),
  Sensor(robot_name:, sensor:),
  forward_distance = sensor.forward_distance,
  hamlet_angle = Coalesce(
    ArgMin{ x.angle -> x.distance :- x in sensor.radar, x.object = "robot", Hamlet(x.label) == true
  } + angle_shift, 0),
  angle_shift = (
    if RobotIndex(robot_name) == 1 then
      0.4
    else if RobotIndex(robot_name) == 2 then
      -0.4
    else
      0
  ),
  hamlet_distance = Coalesce( Min{ x.distance :-  x in sensor.radar, x.object = "robot", Hamlet(x.label) == true }, 200),
  wall_distance = Coalesce(Min{ x.distance :- x in sensor.radar, x.object="wall" }, 200),
  boost = (if Hamlet(robot_name) then 0 else if hamlet_distance > 150 then 0.5 else if hamlet_distance > 70 then 0.3 else if hamlet_distance > 60 then 0 else -0.7),
  dist = (if Hamlet(robot_name) then wall_distance else forward_distance),
  left_engine = 0.6 - 0.3 * I(dist <= 50),
  right_engine = 0.6 - 0.9 * I(dist <= 50);