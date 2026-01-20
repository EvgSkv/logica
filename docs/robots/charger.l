# HELPER FUNCTION: Returns true if a radar ping 'r' is a dead robot.
IsDeadBot(r) = (
  r.object == "robot" && EndsWith(r.label, "_DeadBattery")
);

# HELPER FUNCTION: Returns true if a radar ping 'r' is a charging station.
IsChargingStation(r) = (
  r.object == "beacon" && EndsWith(r.label, "_ChargingStation")
);

# HELPER FUNCTION: Finds the ANGLE of the closest DEAD BOT.
ClosestDeadBotAngle(radar) = ArgMin{
  r.angle -> r.distance :-
    r in radar,
    IsDeadBot(r)==true
};

# HELPER FUNCTION: Finds the ANGLE of the closest CHARGING STATION.
ClosestChargingStationAngle(radar) = ArgMin{
  r.angle -> r.distance :-
    r in radar,
    IsChargingStation(r)==true
};

# A helper function to steer towards a target angle.
SteerTo(target_angle, speed) = {
  left_engine: speed - target_angle,
  right_engine: speed + target_angle
};

# Standard obstacle avoidance logic.
WeightedAverage(k->v) = Sum(k * v) / Sum(k);
FreedomMotion(radar) = WeightedAverage{
  x.distance -> x.angle :- x in radar
};

# Returns true if the robot should be helping a dead bot.
ShouldHelpDeadBot(sensor) = (
  sensor.self.can_charge == true &&
  sensor.self.battery_level >0 &&
  Count{1 :- r in sensor.radar, IsDeadBot(r)==true}>0
);

# Returns true if the robot should be seeking a charging station.
ShouldSeekCharger(sensor) = (
  sensor.self.can_charge == true &&
  sensor.self.battery_level == 0 &&
  Count{1 :- r in sensor.radar, IsChargingStation(r)==true} > 0
);


# --- Main Logic Starts Here (Now Explicit) ---

# PRIORITY 1: A robot that can_charge will go help a dead robot it sees.
Robot(robot_name:, desire:, memory:) :-
  Sensor(robot_name:, sensor:),
  # Check if the conditions for this priority are met.
  ShouldHelpDeadBot(sensor)==true,
  
  # Find the angle to the closest one.
  dead_bot_angle = ClosestDeadBotAngle(sensor.radar),
  
  desire = SteerTo(dead_bot_angle, 1),
  memory = "Going to help a robot in need!";


# PRIORITY 2: If a robot that can_charge has no battery, it seeks a station.
Robot(robot_name:, desire:, memory:) :-
  Sensor(robot_name:, sensor:),
  # Check if the conditions for this priority are met.
  ShouldSeekCharger(sensor)==true,

  # Find the angle to the closest one.
  station_angle = ClosestChargingStationAngle(sensor.radar),

  desire = SteerTo(station_angle, 1),
  memory = "My battery is empty! Seeking a charging station.";


# PRIORITY 3 (DEFAULT): All other robots will just wander around avoiding walls.
Robot(robot_name:, desire:, memory:) :-
  Sensor(robot_name:, sensor:),
  
  ShouldHelpDeadBot(sensor)==false,
  ShouldSeekCharger(sensor)==false,

  freedom = FreedomMotion(sensor.radar),
  speed = 0.5,
  desire = {
    left_engine: speed - freedom+0.1,
    right_engine: speed + freedom
  },
  memory = "Exploring the labyrinth.";