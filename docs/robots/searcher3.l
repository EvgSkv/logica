# --- Physics & Helper Functions ---
WeightedAverage(w -> v) = Sum(w * v) / Sum(w);
FreedomMotion(radar) = WeightedAverage{ x.distance -> x.angle :- x in radar };
AngleDesire(angle, speed) = { left_engine: speed + 0.05 - angle, right_engine: speed + angle };
ValueOrZero(x) = Coalesce(AnyValue(x), 0);

# --- Memory Parsing (The Leader's Database) ---

@Ground(LeaderMemory);
LeaderMemory() = Coalesce(TryCast(leader_memory, l), l) :-
  Memory(robot_name: "R2", memory: leader_memory),
  l = {edges: [], heatmap: [{beacon: "Home", d: 0}]},
  l ~ {edges: [{u: Str, v: Str, d: Num}], heatmap: [{beacon: Str, d: Num}]};

@Ground(StoredEdges);
StoredEdges(u:, v:, d:) :-
  memory = LeaderMemory(),
  {u:, v:, d:} in memory.edges;

@Ground(StoredHeatmap);
StoredHeatmap(beacon:, d:) :-
  memory = LeaderMemory(),
  {beacon:, d:} in memory.heatmap;

# --- Step 1: Update the Topology (Edges) ---

# @Ground forces the engine to compute the distances first, dropping 'robot_name'
# before trying to aggregate the Minimum.
@Ground(ObservedEdges);
ObservedEdges(u: b1, v: b2, d? Min= dist) distinct :-
  Sensor(robot_name:, sensor:),
  radar = sensor.radar,
  x in radar, y in radar,
  x.object == "beacon", y.object == "beacon",
  x.label < y.label,
  b1 = x.label, b2 = y.label,
  d1 = x.distance, d2 = y.distance,
  angle_diff = Abs(x.angle - y.angle),
  dist = Sqrt(d1*d1 + d2*d2 - 2*d1*d2 * Cos(angle_diff));

@Ground(AllEdges);
AllEdges(u, v) Min= d :-
  StoredEdges(u:, v:, d:) | ObservedEdges(u:, v:, d:);

# --- Step 2: Incremental Heatmap Update (Relaxation) ---

@Ground(Graph);
Graph(source, target) = distance :- AllEdges(source, target) == distance;
Graph(source, target) = distance :- AllEdges(target, source) == distance;

@Ground(UpdatedHeatmap);
UpdatedHeatmap(beacon) Min= d :-
  # Option A: The distance we already knew
  StoredHeatmap(beacon:, d:) | 
  # Option B: Distance to neighbor + edge weight
  (StoredHeatmap(beacon: neighbor, d: d_neighbor),
   Graph(neighbor, beacon) == edge_weight,
   d = d_neighbor + edge_weight) |
  # Option C: Hardcode Home
  (beacon == "Home", d == 0);

# --- Memory Serialization ---

@Ground(NewEdgesList);
NewEdgesList() List= {u: u, v: v, d: d} :- AllEdges(u, v) == d;

@Ground(NewHeatmapList);
NewHeatmapList() List= {beacon: b, d: d} :- UpdatedHeatmap(b) == d;

@Ground(NewLeaderMemory);
NewLeaderMemory() = { 
  edges: NewEdgesList(), 
  heatmap: NewHeatmapList() 
};

# --- Navigation (Using the Heatmap) ---

@Ground(RobotSeesBeacons);
RobotSeesBeacons(robot_name) Set= x.label :-
  Sensor(robot_name:, sensor:),
  x in sensor.radar,
  x.object = "beacon";

@Ground(LovelyBeacon);
LovelyBeacon(robot_name) ArgMin= beacon -> distance :-
  beacon in RobotSeesBeacons(robot_name),
  UpdatedHeatmap(beacon) == distance;

@Ground(LovelyBeaconAngle);
LovelyBeaconAngle(robot_name) = ValueOrZero{
  x.angle :-
  x in sensor.radar,
  x.label == LovelyBeacon(robot_name)
} :- Sensor(robot_name:, sensor:);

# --- Robot State & Output ---

# Helper function (not a predicate) doesn't typically need Ground
AppropriateMemory(robot_name) =(
  if robot_name == "R2" then
    ToString(NewLeaderMemory())
  else
    ToString(NewOtherMemory(robot_name))
);

NewOtherMemory(robot_name) = {
  heatmap_size: ToInt64(Count{UpdatedHeatmap()}),
  lovely_angle: LovelyBeaconAngle(robot_name),
  state: NewState(robot_name)
};

NewState(robot_name) = (
  if "Home" in AnyValue{RobotSeesBeacons(robot_name)} && sensor.clock > 20000 then
    "parking"
  else
    memory.state) :- memory = OtherMemory(robot_name), Sensor(robot_name:, sensor:);

@Ground(OtherMemory);
OtherMemory(robot_name) = Coalesce(TryCast(memory, default), default) :-
  default = {heatmap_size: 0, lovely_angle: 0, state: "search"},
  Memory(robot_name:, memory:);

BigEvent(sensor) = ToFloat64(clock % 10000 < 100) :- clock = sensor.clock;

Robot(robot_name:,
      desire:,
      memory: AppropriateMemory(robot_name)) :-
  Memory(robot_name:, memory: old_memory),
  memory = Coalesce(old_memory, "Earth"),
  Sensor(robot_name:, sensor:),
  freedom = FreedomMotion(sensor.radar),
  lovely = (if sensor.clock < 10000 then 0 else LovelyBeaconAngle(robot_name)),
  speed = (
    if sensor.forward_distance < 45 && sensor.forward_object == "wall" then 0 else 0.5
  ),
  rotation_boost = (
    if sensor.forward_distance < 40 && sensor.forward_object == "wall" then
      0.5
    else
      0.3
  ),
  desire = (
    if NewState(robot_name) == "parking" && "Home" in AnyValue{RobotSeesBeacons(robot_name)} then
      AngleDesire(lovely / 5, (sensor.forward_distance - 40 + 10 * Sin(sensor.clock / 40)) / 60 )
    else
      search_desire
  ),
  wiggle = 0.05 * Sin(sensor.clock / 100) + 10 * BigEvent(sensor),
  search_desire = AngleDesire((freedom + lovely + wiggle) * rotation_boost, speed);