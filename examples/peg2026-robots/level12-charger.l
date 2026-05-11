WeightedAverage(k->v) = Sum(k * v) / Sum(k);

# Steer toward open space
FreedomMotion(radar, destination) = WeightedAverage{
  x.distance * desire_factor -> x.angle :-
  x in radar,
  desire_factor == (if x.object == destination then 10.0 else 1.0)
};

Destination(sensor) = (
  if sensor.self.can_charge &&
     sensor.self.battery_level > 50 then
    "robot"
  else if sensor.self.can_charge then
    "beacon"
  else
    "happiness"
);

Robot(robot_name:, desire:, memory: destination) :-
  Sensor(robot_name:, sensor:),
  destination = Destination(sensor),
  freedom = FreedomMotion(sensor.radar, destination),
  speed = 0.5,
  desire = {
    left_engine: speed - freedom + 0.1,
    right_engine: speed + freedom
  };