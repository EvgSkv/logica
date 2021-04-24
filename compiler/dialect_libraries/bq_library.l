->(left:, right:) = {arg: left, value: right};

ArgMin(a) = SqlExpr("ARRAY_AGG({arg} order by {value} limit 1)[OFFSET(0)]",
                    {arg: a.arg, value: a.value});

ArgMax(a) = SqlExpr(
  "ARRAY_AGG({arg} order by {value} desc limit 1)[OFFSET(0)]",
  {arg: a.arg, value: a.value});

ArgMaxK(a, l) = SqlExpr(
  "ARRAY_AGG({arg} order by {value} desc limit {lim})",
  {arg: a.arg, value: a.value, lim: l});

ArgMinK(a, l) = SqlExpr(
  "ARRAY_AGG({arg} order by {value} limit {lim})",
  {arg: a.arg, value: a.value, lim: l});

Array(a) = SqlExpr(
  "ARRAY_AGG({value} order by {arg})",
  {arg: a.arg, value: a.value});
