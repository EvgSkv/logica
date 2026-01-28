# Testing equality of equality to true.

@Engine("bigquery");

Is5(x) = (x == 5);

Test(x) :- Is5(x) == true, x in Range(10);