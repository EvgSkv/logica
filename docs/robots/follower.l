
@Ground(Robot);
Robot(robot_name:,
      desire: {
        left_engine:,
        right_engine:
      },
      memory:) :-
  robot_name = "R1",
  Memory(robot_name:, memory: old_memory),  
  # Just pass memory forward, or reset to remember Earth.
  memory = Coalesce(old_memory, "Earth"),
  Sensor(robot_name:, sensor:),
  forward_distance = sensor.forward_distance,
  ((
    forward_distance > 50,
    left_engine = 1.0,
    right_engine = 1.0
  ) | (
    # Turning one way for now.
    forward_distance <= 50,
    left_engine = 0.5,
    right_engine = -0.5
  ));

Robot(robot_name:,
      desire: {
        left_engine:,
        right_engine:
      },
      memory:) :-
  robot_name = "R2",
  Memory(robot_name:, memory: old_memory),  
  # Just pass memory forward, or reset to remember Earth.
  memory = Coalesce(old_memory, "Earth"),
  Sensor(robot_name:, sensor:),
  angle 1= (x.angle :- x in sensor.radar, x.object = "robot"),
  ((angle is not null,
    left_engine = -angle + 0.7,
    right_engine = angle + 0.7) | (
    angle is null,
    left_engine = 0.6, right_engine = 0.7));

# We must use RecordAsJson to handle the struct-to-JSON conversion
RobotJson(robot_name:, desire: RecordAsJson(desire), memory:) :-
  Robot(robot_name:, desire:, memory:);
