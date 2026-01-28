
RobotPreference(beacons: ["A", "B", "C", "Plumbing Station"], final: "Plumbing Station");
Preference(label) = (
  if label=="A" then
    1
  else if label == "B" then
    2
  else if label == "C" then
    3
  else if label == "Plumbing Station" then
    4
  else
    5
);

Beacon(radar) = ArgMax{x -> Preference(x.label) :-
                       x in radar,
                       x.object = "beacon" };

@Ground(Robot);
Robot(robot_name:,
      desire: {
        left_engine:,
        right_engine:
      },
      memory: RecordAsJson(beacon)) :-
  beacon = Beacon(sensor.radar),
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

# We must use RecordAsJson to handle the struct-to-JSON conversion
RobotJson(robot_name:, desire: RecordAsJson(desire), memory:) :-
  Robot(robot_name:, desire:, memory:);
