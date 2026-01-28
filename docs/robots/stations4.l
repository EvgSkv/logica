
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

LikesBeacon(beacon) = ((beacon is not null) && (t is not null) && (t == "A" || t == "B" || t== "C" || t == "Plumbing Station")) :-
  t = beacon.label;

Finish(beacon) = (beacon.label == "Plumbing Station" && beacon.distance < 30);

Beacon(radar) = ArgMin{x -> Preference(x.label) :-
                       x in radar,
                       x.object = "beacon" };


RobotZ(robot_name:,
      desire:{left_engine:, right_engine:},
      memory: robot_name ++ "/no beacon at all!" ++ ToString(~Beacon(sensor.radar)) ++ "--" ++ ToString(LikesBeacon(beacon))) :-
  Sensor(robot_name:, sensor:),
  left_engine = 0.4,
  right_engine = 0.35,
  beacon = Beacon(sensor.radar);

RobotTTT(robot_name:,
      desire:{left_engine:, right_engine:},
      memory: robot_name ++ "/nope - " ++ RecordAsJson({b:beacon}) ++ "->" ++ ToString("ffff")) :-
  Sensor(robot_name:, sensor:),
  beacon == Beacon(sensor.radar),
  left_engine = 0.4,
  right_engine = 0.35,
  !LikesBeacon(beacon);

Robot(robot_name:,
      desire:{left_engine:, right_engine:},
      memory: robot_name ++ "/" ++ RecordAsJson(beacon)) :-
  Sensor(robot_name:, sensor:),
  beacon = Beacon(sensor.radar),
  left_engine = 0.3 + beacon.angle/3,
  right_engine = 0.3 + -beacon.angle/3,
  LikesBeacon(beacon),
  !Finish(beacon);


Robot(robot_name:,
      desire:{left_engine:, right_engine:},
      memory: robot_name ++ "/nope - at all" ++ RecordAsJson({b:beacon}) ++ "---" ++ ToString(LikesBeacon(beacon))) :-
  Sensor(robot_name:, sensor:),
  beacon == Beacon(sensor.radar),
  freedom = Sum{ x.distance * x.angle :- x in sensor.radar } / Sum{ x.distance :- x in sensor.radar},
  left_engine = 0.7 + freedom, # 0.8 * ToFloat64(sensor.forward_distance < 50),
  right_engine = 0.75,
  !LikesBeacon(beacon);

# We must use RecordAsJson to handle the struct-to-JSON conversion
@Ground(Robot);
RobotJson(robot_name:, desire: RecordAsJson(desire), memory:) :-
  Robot(robot_name:, desire:, memory:);
