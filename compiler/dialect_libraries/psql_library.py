library = """
->(left:, right:) =
  SqlExpr("STRUCT({left} as arg, {right} as value)", {left:, right:});
ArgMin(a) = SqlExpr("(ARRAY_AGG({arg} order by {value}))[1]",
                    {arg: a.arg, value: a.value})
"""
