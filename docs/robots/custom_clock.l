DefaultMem() = {s: 100, mode: "forward"};

@Ground(ParsedMem);
ParsedMem(robot_name) = TryCast(memory, DefaultMem()) :-
  Memory(robot_name:, memory:);

State(robot_name) =  Coalesce(ParsedMem(robot_name), DefaultMem());

NextMode("forward") = "right";
NextMode("right") = "forward";
ModeTime("forward") = 200;
ModeTime("right") = 20;

NewState(robot_name) = {s: s - 1, mode: Coalesce(state.mode, "forward")} :-
  state = State(robot_name),
  s = state.s,
  s > 0;
NewState(robot_name) = {s: ModeTime(mode), mode: mode} :-
  state = State(robot_name),
  s = state.s,
  mode = NextMode(state.mode),
  s == 0;


Robot(robot_name:,
      desire: {
        left_engine: 0.5,
        right_engine: (if state.mode == "forward" then 0.5 else -0.5)
      },
      memory: state) :-
  # Read memory if needed:
  # Memory(robot_name:, memory: old_memory),  
  memory = ("I, " ++ robot_name ++", desire and therefore I am. I see " ++
            sensor.forward_object ++ " is at " ++ ToString(sensor.forward_distance)),
  Sensor(robot_name:, sensor:),
  state == NewState(robot_name);

