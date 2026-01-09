
@Ground(Robot);
Robot(robot_name:,
      desire: {
        left_engine:,
        right_engine:
      },
      memory: "M") :-
  # Memory(robot_name:, memory: old_memory),  
  # Just pass memory forward, or reset to remember Earth.
  Sensor(robot_name:, sensor:),
  forward_distance = sensor.forward_distance,
  1{ x :- x in sensor.radar, x.label="Home", x.distance < 40} is null,
  right_distance = ArgMin{ x.distance -> x.angle :- x in sensor.radar },
  ((
    right_distance > 20,
    left_engine = 0.6,
    right_engine = 0.8
  ) | (
    # Turning one way for now.
    right_distance <= 20,
    left_engine = 0.8,
    right_engine = 0.2
  ));

# We must use RecordAsJson to handle the struct-to-JSON conversion
RobotJson(robot_name:, desire: RecordAsJson(desire), memory:) :-
  Robot(robot_name:, desire:, memory:);
