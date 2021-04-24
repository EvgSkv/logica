library = """
->(left:, right:) = {arg: left, value: right};

ArgMin(a) = SqlExpr("(ARRAY_AGG({arg} order by {value}))[1]",
                    {arg: a.arg, value: a.value})
"""
