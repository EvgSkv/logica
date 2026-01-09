
@Ground(Robot);
Robot(robot_name:,
      desire: {
        left_engine:,
        right_engine:
      },
      memory:) :-
  Memory(robot_name:, memory: old_memory),  
  # Just pass memory forward, or reset to remember Earth.
  memory = ToString(beacon_angle),
  Sensor(robot_name:, sensor:),
  forward_distance = sensor.forward_distance,
  beacon_angle 1= (x.angle :- x in sensor.radar, x.object = "beacon"),
  ((
    beacon_angle is not null,
    left_engine = -beacon_angle,
    right_engine = beacon_angle
  ) | (
    beacon_angle is null && forward_distance > 50,
    left_engine = 1.0,
    right_engine = 1.0
  ) | (
    # Turning one way for now.
    beacon_angle is null && forward_distance <= 50,
    left_engine = 0.5,
    right_engine = -0.5
  ));

# We must use RecordAsJson to handle the struct-to-JSON conversion
RobotJson(robot_name:, desire: RecordAsJson(desire), memory:) :-
  Robot(robot_name:, desire:, memory:);
