
Preference(label) = (
  if label=="A" then
    1
  else if label == "B" then
    2
  else if label == "C" then
    3
  else if label == "Plumbing Station" then
    10
  else
    -1
);
LikesBeacon(beacon) = (Preference(beacon.label) > 0);


PreferenceJ(label) = (
  if label=="A" then
    1
  else if label == "B" then
    2
  else if label == "D" then
    3
  else if label == "Fire Station" then
    10
  else
    -1
);

PreferenceM(label) = (
  if label == "E" then
    1
  else if label == "F" then
    2
  else if label == "Mining" then
    10
  else
    -1
);


Finish(beacon) = (Preference(beacon.label) == 10 && beacon.distance < 30);

Beacon(radar) = ArgMax{x -> Preference(x.label) :-
                       x in radar,
                       x.object = "beacon" };

Juliet := Romeo(Preference: PreferenceJ);
Miner := Romeo(Preference: PreferenceM);

Robot(robot_name:, desire:, memory:) :-
  robot_name == "Romeo",
  Romeo(robot_name:, desire:, memory:);
Robot(robot_name:, desire:, memory:) :-
  robot_name == "Juliet",
  Juliet(robot_name:, desire:, memory:);
Robot(robot_name:, desire:, memory:) :-
  robot_name == "Miner",
  Miner(robot_name:, desire:, memory:);

#Robot(robot_name: "Juliet",
#      desire: {left_engine: 1, right_engine: 1}, memory: "hi!");

#@Ground(Romeo);
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
      memory: robot_name ++ "/nope - at all" ++ RecordAsJson({b:beacon})) :- # ++ "---" ++ ToString(LikesBeacon(beacon))) :-
  Sensor(robot_name:, sensor:),
  beacon == Beacon(sensor.radar),
  freedom = Sum{ x.distance * x.angle :- x in sensor.radar } / Sum{ x.distance :- x in sensor.radar},
  left_engine = 0.7 + freedom, # 0.8 * ToFloat64(sensor.forward_distance < 50),
  right_engine = 0.75,
  (beacon is null | !LikesBeacon(beacon));



# We must use RecordAsJson to handle the struct-to-JSON conversion
@Ground(Robot);
RobotJson(robot_name:, desire: RecordAsJson(desire), memory:) :-
  Robot(robot_name:, desire:, memory:);
