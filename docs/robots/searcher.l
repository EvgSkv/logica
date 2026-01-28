
WeightedAverage(w -> v) = Sum(w * v) / Sum(w);

FreedomMotion(radar) = WeightedAverage{ x.distance -> x.angle :- x in radar };

AngleDesire(angle, speed) = {
  left_engine: speed + 0.05 - angle,
  right_engine: speed + angle
};

LeaderMemory() = Coalesce(TryCast(leader_memory, l), {beacons: [{beacon: "Home", distance: 0}]}) :-
  Memory(robot_name: "R2",
         memory: leader_memory),
  l = {beacons: []},
  l ~ {beacons: [{beacon: Str, distance: Num}]};

Beacons(beacon:, distance:) :-
  memory = LeaderMemory(),
  {beacon:, distance:} in memory.beacons;

NewBeacons(beacon:, distance? Min= distance) distinct :-
  Beacons(beacon:, distance:);

@Ground(LovelyBeacon);
LovelyBeacon(robot_name) ArgMin= beacon -> distance :-
  beacon in RobotSeesBeacons(robot_name),
  Beacons(beacon:, distance:);

ValueOrZero(x) = Coalesce(AnyValue(x), 0);

@Ground(LovelyBeaconAngle);
LovelyBeaconAngle(robot_name) = ValueOrZero{
  x.angle :-
  x in sensor.radar,
  x.label == LovelyBeacon(robot_name)
} :- Sensor(robot_name:, sensor:);

@Ground(NewBeacons);
NewBeacons(beacon: b1, distance? Min= total_distance) distinct :-
  Sensor(robot_name:, sensor:),
  radar = sensor.radar,
  x in radar,
  y in radar,
  x.object == "beacon",
  y.object == "beacon",
  x.label = b1,
  y.label = b2,
  # Get the known cumulative distance of the reference beacon (b2)
  Beacons(beacon: b2, distance: known_b2_dist),
  
  # Extract local polar coordinates
  d1 = x.distance,
  d2 = y.distance,
  angle_diff = x.angle - y.angle,

  # Law of Cosines to find distance between b1 and b2
  segment_dist = Sqrt(d1 * d1 + d2 * d2 - 2 * d1 * d2 * Cos(angle_diff)),
  
  # The new total distance is the known path + this new segment
  total_distance = known_b2_dist + segment_dist;

NewBeaconsList() Array= beacon -> {beacon:, distance:} :- NewBeacons(beacon:, distance:);

NewLeaderMemory() = {beacons:  NewBeaconsList() };

RobotSeesBeacons(robot_name) Set= x.label :-
  Sensor(robot_name:, sensor:),
  x in sensor.radar,
  x.object = "beacon";

AppropriateMemory(robot_name) =(
  if robot_name == "R2" then
    ToString(NewLeaderMemory())
  else
    ToString(NewOtherMemory(robot_name))
);

NewOtherMemory(robot_name) = {beacons_seen: ToInt64( Sum{1 :- Beacons()} ),
                              lovely_angle: LovelyBeaconAngle(robot_name),
                              state: NewState(robot_name)};


NewState(robot_name) = (
  if "Home" in AnyValue{RobotSeesBeacons(robot_name)} && sensor.clock > 50000 then
    "parking"
  else
    memory.state) :- memory = OtherMemory(robot_name), Sensor(robot_name:, sensor:);

@Ground(OtherMemory);
OtherMemory(robot_name) = Coalesce(TryCast(memory, default), default) :-
  default = {beacons_seen: 0, lovely_angle: 0, state: "search"},
  Memory(robot_name:, memory:);


Robot(robot_name:,
      desire:,
      memory: AppropriateMemory(robot_name)) :-
  Memory(robot_name:, memory: old_memory),  
  # Just pass memory forward, or reset to remember Earth.
  memory = Coalesce(old_memory, "Earth"),
  Sensor(robot_name:, sensor:),
  freedom = FreedomMotion(sensor.radar),
  lovely = LovelyBeaconAngle(robot_name),
  speed = (
    if sensor.forward_distance < 45 && sensor.forward_object == "wall" then
      0
    else
      0.5
  ),
  desire = (
    if NewState(robot_name) == "parking" then
      AngleDesire(0, 1.0)
    else
      search_desire
  ),
  wiggle = 0.1 * Sin(sensor.clock / 100),
  search_desire = AngleDesire((freedom + lovely + wiggle) / 3, speed);