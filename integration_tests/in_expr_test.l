# Testing 'in' as a classic function.

@Engine("bigquery");

Test(x, x in [1,2,3]) :- x in Range(10);