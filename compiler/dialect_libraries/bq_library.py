library = """
->(left:, right:) = {arg: left, value: right};
  #SqlExpr("STRUCT({left} as arg, {right} as value)", {left:, right:});
ArgMin(a) = SqlExpr("ARRAY_AGG({arg} order by {value} limit 1)[OFFSET(0)]",
                    {arg: a.arg, value: a.value});
"""
