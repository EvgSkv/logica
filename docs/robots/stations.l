
RobotPreference(beacons: ["A", "B", "C", "Plumbing Station"], final: "Plumbing Station");
Preference(label) = 1{i :- i in Range(Size(beacons)), beacons[i] == label} :-
  RobotPreference(beacons:);

Beacon(radar, angle: beacon.angle, distance: beacon.distance) :-
  beacon = ArgMax{ x -> Preference(x.label) :- x in radar, x.object = "beacon" }, beacon is not null;

Sweet(radar) = !~ (x in radar, x.label = final, x.distance < 20) :-
  RobotPreference(final:);

JulietPreference(beacons: ["A", "B", "D", "Fire Station"], final: "Fire Station");
MinerPreference(beacons: ["E", "B", "Mining"], final: "Mining");


Juliet := Romeo(RobotPreference: JulietPreference);
Miner := Romeo(RobotPreference: MinerPreference);

Robot(robot_name: "Romeo",
      desire:,
      memory:) :- Romeo(robot_name: "Romeo", desire:, memory:);
Robot(robot_name: "Juliet",
      desire:,
      memory:) :- Juliet(robot_name: "Juliet", desire:, memory:);
Robot(robot_name: "Miner",
      desire:,
      memory:) :- Miner(robot_name: "Miner", desire:, memory:);


Romeo(robot_name:,
      desire: {
        left_engine:,
        right_engine:
      },
      memory: robot_name) :-
  RobotPreference(beacons:),
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

Romeo(robot_name:,
      desire: {left_engine:, right_engine:},
      memory: "I see radar!" ++ RecordAsJson({angle:, distance:, m:})) :-
  Beacon(sensor.radar, angle:, distance:),
  !Sweet(sensor.radar),
  m = Least(1, distance / 30.0) / 5.0,
  left_engine = angle * m + 0.8, right_engine=-angle * m + 0.8,
  Sensor(robot_name:, sensor:);

# We must use RecordAsJson to handle the struct-to-JSON conversion
@Ground(Robot);
RobotJson(robot_name:, desire: RecordAsJson(desire), memory:) :-
  Robot(robot_name:, desire:, memory:);
