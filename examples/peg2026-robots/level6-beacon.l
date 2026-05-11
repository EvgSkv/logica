WeightedAverage(k->v) = Sum(k * v) / Sum(k);

# Steer toward open space
FreedomMotion(radar, best_beacon:) = WeightedAverage{
  x.distance * desire_factor -> x.angle :-
  x in radar,
  desire_factor == (if x.label == best_beacon then 20.0 else 1.0)
} :-
  best_beacon = Max{b.label :- b in radar, b.object == "beacon"};


Robot(robot_name:, desire:, memory: "") :-
  Sensor(robot_name:, sensor:, memory:),
  freedom = FreedomMotion(sensor.radar, best_beacon:) / 2.0,
  speed = 0.5,
  blissful = (if (sensor.forward_label == "Sweet" &&
                  sensor.forward_distance < 30) then 0 else 1),
  desire = {
    left_engine: blissful * (speed - freedom - 0.02),
    right_engine: blissful * (speed + freedom)
  };