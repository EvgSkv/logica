# --- Core Math & Physics ---

WeightedAverage(w -> v) = Sum(w * v) / Sum(w);

FreedomMotion(radar) = WeightedAverage{ x.distance -> x.angle :- x in radar };

AngleDesire(angle, speed) = {
  left_engine: speed - angle,
  right_engine: speed + angle
};

ValueOrZero(x) = Coalesce(AnyValue(x), 0);

# --- Leader Memory (Database) ---

@Ground(LeaderMemory);
LeaderMemory() = Coalesce(TryCast(leader_memory, schema), schema) :-
  Memory(robot_name: "R2", memory: leader_memory),
  schema = {edges: [], heatmap: [{beacon: "Home", d: 0}]},
  schema ~ {edges: [{u: Str, v: Str, d: Num}], heatmap: [{beacon: Str, d: Num}]};

@Ground(StoredEdges);
StoredEdges(u:, v:, d:) :-
  memory = LeaderMemory(),
  {u:, v:, d:} in memory.edges;

@Ground(StoredHeatmap);
StoredHeatmap(beacon:, d:) :-
  memory = LeaderMemory(),
  {beacon:, d:} in memory.heatmap;

# --- Topology Mapping (Edges) ---

@Ground(ObservedEdges);
ObservedEdges(u: b1, v: b2, d? Min= dist) distinct :-
  Sensor(robot_name:, sensor:),
  x in sensor.radar,
  y in sensor.radar,
  x.object == "beacon",
  y.object == "beacon",
  x.label < y.label,
  b1 = x.label,
  b2 = y.label,
  # Law of Cosines
  d1 = x.distance,
  d2 = y.distance,
  angle_diff = Abs(x.angle - y.angle),
  dist = Sqrt(d1*d1 + d2*d2 - 2*d1*d2 * Cos(angle_diff));

@Ground(AllEdges);
AllEdges(u, v) Min= d :-
  StoredEdges(u:, v:, d:) | ObservedEdges(u:, v:, d:);

# --- Distributed Bellman-Ford (Heatmap) ---

@Ground(Graph);
Graph(source, target) = d :- AllEdges(source, target) == d;
Graph(source, target) = d :- AllEdges(target, source) == d;

@Ground(UpdatedHeatmap);
UpdatedHeatmap(beacon) Min= d :-
  StoredHeatmap(beacon:, d:) |
  (beacon == "Home", d == 0) |
  (StoredHeatmap(beacon: neighbor, d: d_neighbor),
   Graph(neighbor, beacon) == edge_weight,
   d = d_neighbor + edge_weight);

# --- Serialization ---

@Ground(NewLeaderMemory);
NewLeaderMemory() = {
  edges:   List{ {u: u, v: v, d: d} :- AllEdges(u, v) == d },
  heatmap: List{ {beacon: b, d: d}  :- UpdatedHeatmap(b) == d }
};

# --- Navigation Lookup ---

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

# --- State Management ---

NewState(robot_name) = (
  if "Home" in AnyValue{RobotSeesBeacons(robot_name)} && sensor.clock > 20000 then
    "parking"
  else
    memory.state
) :-
  memory = OtherMemory(robot_name),
  Sensor(robot_name:, sensor:);

@Ground(OtherMemory);
OtherMemory(robot_name) = Coalesce(TryCast(memory, default), default) :-
  default = {heatmap_size: 0, lovely_angle: 0, state: "search"},
  Memory(robot_name:, memory:);

AppropriateMemory(robot_name) =(
  if robot_name == "R2" then
    ToString(NewLeaderMemory())
  else
    ToString(NewOtherMemory(robot_name))
);

NewOtherMemory(robot_name) = {
  heatmap_size: ToInt64(Count{UpdatedHeatmap()}),
  lovely_angle: LovelyBeaconAngle(robot_name),
  state:        NewState(robot_name)
};

# --- Main Control Loop ---

Robot(robot_name:, desire:, memory: AppropriateMemory(robot_name)) :-
  Memory(robot_name:, memory: old_mem),
  Sensor(robot_name:, sensor:),
  
  # Inputs
  memory = Coalesce(old_mem, "Earth"),
  freedom = FreedomMotion(sensor.radar),
  target_angle = LovelyBeaconAngle(robot_name),
  
  # Logic Flags
  is_stuck   = (sensor.forward_distance < 45 && sensor.forward_object == "wall"),
  is_parking = (NewState(robot_name) == "parking" && "Home" in AnyValue{RobotSeesBeacons(robot_name)}),
  is_early   = (sensor.clock < 10000),
  
  # Behavior: Base Speed
  base_speed = (if is_stuck then 0 else 0.5),
  
  # Behavior: Parking
  park_error  = sensor.forward_distance - 40 + 10 * Sin(sensor.clock / 40),
  park_desire = AngleDesire(target_angle / 5, park_error / 60),

  # Behavior: Search
  lovely_pull    = (if is_early then 0 else target_angle),
  big_event      = ToFloat64(sensor.clock % 10000 < 100),
  wiggle         = 0.1 * Sin(sensor.clock / 600) + 10 * big_event,
  rotation_boost = (if is_stuck then 0.5 else 0.3),
  
  search_desire  = AngleDesire(
    (freedom + lovely_pull + wiggle) * rotation_boost, 
    base_speed
  ),

  desire = (if is_parking then park_desire else search_desire);