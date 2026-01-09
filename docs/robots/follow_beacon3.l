
Beacon(radar) = beacon.angle:-
  beacon = ArgMax{ x -> x.label :- x in radar, x.object = "beacon" }, beacon is not null;

Sweet(radar) = !~ (x in radar, x.label = "Sweet", x.distance < 20);

# No beacon.
Robot(robot_name:,
      desire: {
        left_engine:,
        right_engine:
      },
      memory: "No beacon :(") :-
  Sensor(robot_name:, sensor:),
  !Sweet(sensor.radar),
  ~Beacon(sensor.radar),
  forward_distance = sensor.forward_distance,
  ((
    forward_distance > 50,
    left_engine = 1.0,
    right_engine = 1.0
  ) | (
    # Turning one way for now.
    forward_distance <= 50,
    left_engine = -0.06,
    right_engine = 0.06
  ));

# Beacon!
Robot(robot_name:,
      desire: {left_engine:, right_engine:},
      memory: "Beacon! :D") :-
  Sensor(robot_name:, sensor:),
  !Sweet(sensor.radar),
  left_engine = 0.8 - Beacon(sensor.radar),
  right_engine = 0.8 + Beacon(sensor.radar);
