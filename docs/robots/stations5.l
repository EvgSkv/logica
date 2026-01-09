
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


PreferenceJ(label) = (
  if label=="A" then
    1
  else if label == "B" then
    2
  else if label == "D" then
    3
  else if label == "Fire Station" then
    4
  else
    5
);
LikesBeaconJ(beacon) = ((beacon is not null) && (t is not null) && (t == "A" || t == "B" || t== "D" || t == "Fire Station")) :-
  t = beacon.label;


PreferenceM(label) = (
  if label == "E" then
    1
  else if label == "Mining" then
    2
  else
    3
);
LikesBeaconM(beacon) = ((beacon is not null) && (t is not null) && (t == "E" || t == "Mining")) :-
  t = beacon.label;


Finish(beacon) = (beacon.label == "Plumbing Station" && beacon.distance < 30);
FinishJ(beacon) = (beacon.label == "Fire Station" && beacon.distance < 30);
FinishM(beacon) = (beacon.label == "Mining" && beacon.distance < 30);

Beacon(radar) = ArgMin{x -> Preference(x.label) :-
                       x in radar,
                       x.object = "beacon" };

Juliet := Romeo(LikesBeacon: LikesBeaconJ, Preference: PreferenceJ, Finish: FinishJ);
Miner := Romeo(LikesBeacon: LikesBeaconM, Preference: PreferenceM, Finish: FinishM);

Robot(robot_name:, desire:, memory:) :-
  robot_name == "Romeo",
  Romeo(robot_name:, desire:, memory:);
Robot(robot_name:, desire:, memory:) :-
  robot_name == "Juliet",
  Juliet(robot_name:, desire:, memory:);
Robot(robot_name:, desire:, memory:) :-
  robot_name == "Miner",
  Miner(robot_name:, desire:, memory:);

Romeo(robot_name:,
      desire:{left_engine:, right_engine:},
      memory: robot_name ++ "/" ++ RecordAsJson(beacon)) :-
  Sensor(robot_name:, sensor:),
  beacon = Beacon(sensor.radar),
  left_engine = 0.3 + beacon.angle/3,
  right_engine = 0.3 + -beacon.angle/3,
  LikesBeacon(beacon),
  !Finish(beacon);


Romeo(robot_name:,
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
