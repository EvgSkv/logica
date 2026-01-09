@Ground(Robot);
Robot(robot_name:,
      desire: {
        left_engine:,
        right_engine:
      },
      memory:) :-
  Memory(robot_name:, memory: old_memory),  
  # Just pass memory forward, or reset to remember Earth.
  memory = Coalesce(old_memory, "Earth"),
  Sensor(robot_name:, sensor:),
  d = Min{x.distance :- x in sensor.radar, Abs(x.angle) < 0.3},
  side = 2 * (NaturalHash(robot_name ++ "-" ++ ToString(sensor.clock - sensor.clock % 400)) % 2) - 1,
  ((
    d > 50,
    left_engine = 1.0,
    right_engine = 1.0
  ) | (
    # Turning one way for now.
    d <= 50,
    left_engine = 0.5 * side,
    right_engine = -0.5 * side
  ));

# We must use RecordAsJson to handle the struct-to-JSON conversion
RobotJson(robot_name:, desire: RecordAsJson(desire), memory:) :-
  Robot(robot_name:, desire:, memory:);
