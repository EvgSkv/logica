library = """
->(left:, right:) = {arg: left, value: right};

# All ORDER BY arguments are wrapped, to avoid confusion with
# column index.
ArgMin(a) = SqlExpr("ARRAY_AGG({arg} order by [{value}][offset(0)] limit 1)[OFFSET(0)]",
                    {arg: a.arg, value: a.value});

ArgMax(a) = SqlExpr(
  "ARRAY_AGG({arg} order by  [{value}][offset(0)] desc limit 1)[OFFSET(0)]",
  {arg: a.arg, value: a.value});

ArgMaxK(a, l) = SqlExpr(
  "ARRAY_AGG({arg} order by  [{value}][offset(0)] desc limit {lim})",
  {arg: a.arg, value: a.value, lim: l});

ArgMinK(a, l) = SqlExpr(
  "ARRAY_AGG({arg} order by  [{value}][offset(0)] limit {lim})",
  {arg: a.arg, value: a.value, lim: l});

Array(a) = SqlExpr(
  "ARRAY_AGG({value} order by [{arg}][offset(0)])",
  {arg: a.arg, value: a.value});

"""
