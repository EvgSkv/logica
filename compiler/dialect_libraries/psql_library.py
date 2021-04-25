library = """
->(left:, right:) = {arg: left, value: right};

ArgMin(a) = SqlExpr("(ARRAY_AGG({arg} order by {value}))[1]",
                    {arg: a.arg, value: a.value});

ArgMax(a) = SqlExpr(
  "(ARRAY_AGG({arg} order by {value} desc))[1]",
  {arg: a.arg, value: a.value});

ArgMaxK(a, l) = SqlExpr(
  "(ARRAY_AGG({arg} order by {value} desc))[1:{lim}]",
  {arg: a.arg, value: a.value, lim: l});

ArgMinK(a, l) = SqlExpr(
  "(ARRAY_AGG({arg} order by {value}))[1:{lim}]",
  {arg: a.arg, value: a.value, lim: l});

Array(a) = SqlExpr(
  "ARRAY_AGG({value} order by {arg})",
  {arg: a.arg, value: a.value});

"""
