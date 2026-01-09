
Beacon(radar, angle: beacon.angle, distance: beacon.distance) :-
  beacon = ArgMax{ x -> x.label :- x in radar, x.object = "beacon" }, beacon is not null;

Sweet(radar) = !~ (x in radar, x.label = "Sweet", x.distance < 20);

Robot(robot_name:,
      desire: {
        left_engine:,
        right_engine:
      },
      memory: "No radar") :-
  Memory(robot_name:, memory: old_memory),
  !Sweet(sensor.radar),
  # Just pass memory forward, or reset to remember Earth.
  # memory = Coalesce(old_memory, "Earth"),
  Sensor(robot_name:, sensor:),
  ~Beacon(sensor.radar),
  forward_distance = sensor.forward_distance,
  ((
    forward_distance > 50,
    left_engine = 1.0,
    right_engine = 1.0
  ) | (
    # Turning one way for now.
    forward_distance <= 50,
    left_engine = -0.03,
    right_engine = 0.03
  ));

Robot(robot_name:,
      desire: {left_engine:, right_engine:},
      memory: "I see radar!" ++ RecordAsJson({angle:, distance:, m:})) :-
  Beacon(sensor.radar, angle:, distance:),
  !Sweet(sensor.radar),
  m = Least(1, distance / 30.0),
  left_engine = angle * m + 0.8, right_engine=-angle * m +0.8,
  Sensor(robot_name:, sensor:);

# We must use RecordAsJson to handle the struct-to-JSON conversion
@Ground(Robot);
RobotJson(robot_name:, desire: RecordAsJson(desire), memory:) :-
  Robot(robot_name:, desire:, memory:);
